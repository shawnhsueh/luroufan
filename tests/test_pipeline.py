import json

import pytest

from pipeline import build, config, discover, extract, fetch_menus


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


def test_menu_links_same_domain_and_pdf_first():
    html = """
      <a href="/about">About</a>
      <a href="/products">菜單</a>
      <a href="/menus/dinner">Dinner</a>
      <a href="https://www.example.com/files/food-menu.pdf">Download</a>
      <a href="https://instagram.com/menu">Insta</a>
      <a href="https://example.popmenu.com/menu">Order</a>
      <img src="/img/happy-menu.jpg" alt="Our menu">
      <img src="data:image/svg+xml;base64,AAAA" alt="menu">
      <iframe src="https://menu.example.com/food"></iframe>
      <a href="/menus/dinner/">Dinner again</a>
    """
    pages, images = fetch_menus.menu_links(html, "https://example.com/")
    assert pages[0].endswith("food-menu.pdf")
    assert "https://example.com/menus/dinner" in pages
    assert "https://example.com/products" in pages  # Chinese link text
    assert "https://example.popmenu.com/menu" in pages
    assert "https://menu.example.com/food" in pages  # embedded menu on a subdomain
    assert pages.count("https://example.com/menus/dinner") == 1
    assert not any("instagram" in p or "about" in p for p in pages)
    assert images == ["https://example.com/img/happy-menu.jpg"]


def test_price_pattern_ignores_addresses():
    text = ("滷肉飯 小30/大40\n控肉飯 NT$55\n雞肉飯40\n貢丸湯 30元\n排骨飯 95\n"
            "台北市大安區忠孝東路四段216巷27弄3號\n(02) 2771-1234\n2026年10月")
    assert len(fetch_menus.PRICE.findall(text)) == 5


def test_is_social():
    assert fetch_menus.is_social("https://www.facebook.com/Shezi.Island")
    assert fetch_menus.is_social("https://m.facebook.com/x")
    assert fetch_menus.is_social("https://instagram.com/x")
    assert not fetch_menus.is_social("https://www.jinfeng.com.tw/")
    assert not fetch_menus.is_social("https://notfacebook.com/")


def test_html_text_drops_scripts():
    text = fetch_menus.html_text("<html><body><script>var x=1</script><p>滷肉飯 35</p></body></html>")
    assert text == "滷肉飯 35"


@pytest.mark.parametrize(
    "sources, expected",
    [
        ([{"error": "HTTP 404"}], "fetch_failed"),
        ([{"kind": "html", "text_chars": 900, "mentions": 0}, {"kind": "html", "text_chars": 500, "mentions": 2}], "mentions"),
        ([{"kind": "html", "text_chars": 900, "mentions": 0}, {"kind": "pdf", "text_chars": 10, "mentions": 0}], "needs_vision"),
        ([{"kind": "html", "text_chars": 1000, "mentions": 0, "prices": 2}], "menu_not_found"),
        ([{"kind": "html", "text_chars": 900, "mentions": 0, "prices": 30}], "no_mention"),
    ],
)
def test_classify(sources, expected):
    assert fetch_menus.classify(sources) == expected


def test_snippets_merge_overlapping_windows():
    text = "A" * 5000 + "滷肉飯 35" + "B" * 100 + "肉燥飯 40" + "C" * 5000
    out = extract.snippets(text)
    assert "[...]" not in out  # both mentions fall in one window
    assert "滷肉飯 35" in out and "肉燥飯 40" in out
    assert len(out) < 2 * extract.SNIPPET_RADIUS + 200


def _setup(tmp_path, monkeypatch):
    for name in ["RESTAURANTS_FILE", "MENU_STATUS_FILE", "PRICES_FILE", "OVERRIDES_FILE", "REVIEW_FILE", "GEOJSON_FILE"]:
        monkeypatch.setattr(config, name, tmp_path / getattr(config, name).name)
    monkeypatch.setattr(config, "ROOT", tmp_path)
    monkeypatch.setattr(config, "MENUS_DIR", tmp_path / "menus")


def test_build_content_and_hash_stable(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    d = config.MENUS_DIR / "p1"
    d.mkdir(parents=True)
    (d / "01.txt").write_text("飯類\n滷肉飯 小35\n雞肉飯 40")
    (d / "manifest.json").write_text(json.dumps({"sources": [
        {"url": "https://x.com", "kind": "html", "file": "00.html", "text_file": "00.txt", "text_chars": 0, "mentions": 0},
        {"url": "https://x.com/menu", "kind": "html", "file": "01.html", "text_file": "01.txt", "text_chars": 40, "mentions": 1},
    ]}))
    place = {"place_id": "p1", "name": "X", "address": "台北市中山區南京東路一段1號", "website": "https://x.com"}
    blocks, h1 = extract.build_content(place, "mentions")
    _, h2 = extract.build_content(place, "mentions")
    assert h1 == h2
    assert "滷肉飯 小35" in blocks[-1]["text"]
    assert 'url="https://x.com/menu"' in blocks[-1]["text"]


def test_build_applies_overrides_and_range(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    places = [
        {"place_id": pid, "name": pid, "lat": 25.04, "lng": 121.56, "address": "a", "website": None,
         "google_maps_url": None, "price_level": "PRICE_LEVEL_MODERATE", "rating": 4.5}
        for pid in ("ok", "huge", "manual", "excluded", "none")
    ]
    item = lambda p: [{"dish_name": "滷肉飯", "price": p, "size": "小", "portion_note": None, "is_set_meal": False}]
    prices = [
        {"place_id": "ok", "benchmark_price": 35, "items": item(35), "confidence": "low", "has_lurou": True},
        {"place_id": "huge", "benchmark_price": 900, "items": item(900), "confidence": "high", "has_lurou": True},
        {"place_id": "manual", "benchmark_price": None, "items": [], "confidence": "low", "has_lurou": True},
        {"place_id": "excluded", "benchmark_price": 40, "items": item(40), "confidence": "high", "has_lurou": True},
    ]
    config.write_jsonl(config.RESTAURANTS_FILE, places)
    config.write_jsonl(config.PRICES_FILE, prices)
    config.OVERRIDES_FILE.write_text(
        "place_id,benchmark_price,dish_name,exclude,note\nmanual,45,魯肉飯(小),,現場確認\nexcluded,,,true,\n"
    )
    build.main([])
    feats = {f["properties"]["id"]: f["properties"] for f in json.loads(config.GEOJSON_FILE.read_text())["features"]}
    assert set(feats) == {"ok", "manual"}
    assert feats["ok"]["dish"] == "滷肉飯" and feats["ok"]["price"] == 35 and feats["ok"]["price_level"] == 2
    assert feats["manual"]["price"] == 45 and feats["manual"]["dish"] == "魯肉飯(小)"
    review = config.REVIEW_FILE.read_text()
    assert "huge" in review and "price out of range" in review and "low confidence" in review
