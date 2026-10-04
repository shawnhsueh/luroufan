import json

import pytest

from pipeline import build, config, discover, extract


def test_grid_cells_cover_bbox():
    cells = discover.grid_cells(2, 3)
    south, west, north, east = config.BBOX
    assert len(cells) == 6
    assert cells[0]["low"] == {"latitude": south, "longitude": west}
    assert cells[-1]["high"]["latitude"] == pytest.approx(north)
    assert cells[-1]["high"]["longitude"] == pytest.approx(east)


def test_locality():
    taipei = {"addressComponents": [
        {"longText": "大安區", "types": ["administrative_area_level_2", "political"]},
        {"longText": "臺北市", "types": ["administrative_area_level_1", "political"]},
    ]}
    new_taipei = {"addressComponents": [{"longText": "新北市", "types": ["administrative_area_level_1", "political"]}]}
    assert discover.locality(taipei) in config.ALLOWED_LOCALITIES
    assert discover.locality(new_taipei) not in config.ALLOWED_LOCALITIES
    assert discover.locality({}) is None


def test_cache_key_includes_field_mask(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path)
    calls = []
    monkeypatch.setattr(discover, "_post", lambda client, body: calls.append(body) or {"places": []})
    cell = discover.grid_cells(1, 1)[0]
    discover.search(None, "滷肉飯", cell, None)
    discover.search(None, "滷肉飯", cell, None)
    assert len(calls) == 1  # second call is cached
    monkeypatch.setattr(config, "PLACES_FIELDS", config.PLACES_FIELDS + ",places.photos")
    discover.search(None, "滷肉飯", cell, None)
    assert len(calls) == 2  # a different field mask is a different cache entry


def test_to_reviews_prefers_translated_text():
    place = {"id": "p1", "reviews": [
        {"rating": 5, "text": {"text": "滷肉飯好吃"}, "originalText": {"text": "Lu rou fan is great"},
         "publishTime": "2026-05-01T10:00:00Z", "authorAttribution": {"displayName": "A", "uri": "u"}},
        {"rating": 3, "originalText": {"text": "普通"}},
        {"rating": 4},
    ]}
    out = discover.to_reviews(place)
    assert [r["text"] for r in out["reviews"]] == ["滷肉飯好吃", "普通"]
    assert out["reviews"][0]["author"] == "A"


PLACE = {"place_id": "p1", "name": "X", "address": "台北市中山區南京東路一段1號"}


def test_build_content_needs_a_mention_and_hash_is_stable():
    assert extract.build_content(PLACE, [{"rating": 5, "text": "排骨飯很好吃", "publish_time": "2026-01-02T00:00:00Z"}]) is None
    reviews = [
        {"rating": 5, "text": "魯肉飯小碗35元，肥瘦剛好", "publish_time": "2026-01-02T00:00:00Z"},
        {"rating": 2, "text": "服務很差", "publish_time": "2024-06-30T00:00:00Z"},
    ]
    blocks, h1 = extract.build_content(PLACE, reviews)
    _, h2 = extract.build_content(PLACE, reviews)
    assert h1 == h2
    text = blocks[-1]["text"]
    assert 'stars="5" date="2026-01-02"' in text and "魯肉飯小碗35元" in text
    assert "服務很差" in text  # all reviews go along for context


def _setup(tmp_path, monkeypatch):
    for name in ["RESTAURANTS_FILE", "REVIEWS_FILE", "RATINGS_FILE", "OVERRIDES_FILE", "REVIEW_FILE", "GEOJSON_FILE"]:
        monkeypatch.setattr(config, name, tmp_path / getattr(config, name).name)
    monkeypatch.setattr(config, "ROOT", tmp_path)


def test_build_applies_overrides_ranges_and_sorting(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    places = [
        {"place_id": pid, "name": pid, "lat": 25.04, "lng": 121.56, "address": "a", "website": None,
         "google_maps_url": None, "price_level": "PRICE_LEVEL_INEXPENSIVE", "rating": 4.5, "rating_count": 100}
        for pid in ("good", "ok", "pricey", "manual", "excluded", "unscored")
    ]
    rate = lambda pid, score, price=None, conf="high": {
        "place_id": pid, "status": "ok", "mentions": 3, "score": score, "summary": "滷汁香", "price": price,
        "price_date": "2026-01-02" if price else None, "latest_mention": "2026-01-02", "confidence": conf, "notes": None}
    ratings = [rate("good", 4.6, 35), rate("ok", 3.2, conf="low"), rate("pricey", 4.0, 900),
               rate("manual", None), rate("excluded", 5.0), rate("unscored", None)]
    config.write_jsonl(config.RESTAURANTS_FILE, places)
    config.write_jsonl(config.RATINGS_FILE, ratings)
    config.OVERRIDES_FILE.write_text("place_id,score,price,exclude,note\nmanual,4.2,40,,現場確認\nexcluded,,,true,\n")
    build.main([])
    feats = [f["properties"] for f in json.loads(config.GEOJSON_FILE.read_text())["features"]]
    assert [f["id"] for f in feats] == ["good", "manual", "pricey", "ok"]  # highest score first
    by_id = {f["id"]: f for f in feats}
    assert by_id["good"]["price"] == 35 and by_id["good"]["price_level"] == 1
    assert by_id["manual"]["score"] == 4.2 and by_id["manual"]["price"] == 40 and by_id["manual"]["score_source"] == "manual"
    assert by_id["pricey"]["price"] is None  # out-of-range price dropped, place kept
    review = config.REVIEW_FILE.read_text()
    assert "price out of range" in review and "low confidence" in review
