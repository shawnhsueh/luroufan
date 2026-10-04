"""Step 3: merge restaurants, review ratings and manual overrides into the map's GeoJSON."""

import csv
import json

from . import config

PRICE_LEVELS = {
    "PRICE_LEVEL_INEXPENSIVE": 1,
    "PRICE_LEVEL_MODERATE": 2,
    "PRICE_LEVEL_EXPENSIVE": 3,
    "PRICE_LEVEL_VERY_EXPENSIVE": 4,
}


def read_overrides() -> dict[str, dict]:
    if not config.OVERRIDES_FILE.exists():
        return {}
    with config.OVERRIDES_FILE.open() as f:
        return {row["place_id"]: row for row in csv.DictReader(f) if row.get("place_id")}


def main(argv: list[str] | None = None) -> None:
    places = config.read_jsonl(config.RESTAURANTS_FILE)
    reviews = {r["place_id"]: r["reviews"] for r in config.read_jsonl(config.REVIEWS_FILE)}
    ratings = {r["place_id"]: r for r in config.read_jsonl(config.RATINGS_FILE)}
    overrides = read_overrides()

    features, review = [], []
    for place in places:
        pid = place["place_id"]
        rating = ratings.get(pid, {})
        override = overrides.get(pid, {})
        if override.get("exclude", "").strip().lower() in ("1", "true", "yes"):
            continue

        score, price, confidence = rating.get("score"), rating.get("price"), rating.get("confidence")
        price_date = rating.get("price_date")
        source = "reviews"
        if override.get("score"):
            score, confidence, source = float(override["score"]), "high", "manual"
        if override.get("price"):
            price, price_date = round(float(override["price"])), None
        if score is None:
            continue
        score = min(max(score, config.MIN_SCORE), config.MAX_SCORE)

        flag = lambda reason: review.append({"place_id": pid, "name": place["name"], "score": score, "price": price,
                                             "reason": reason, "summary": rating.get("summary"), "notes": rating.get("notes")})
        if price is not None and not config.PRICE_MIN <= price <= config.PRICE_MAX and not override.get("price"):
            flag("price out of range")
            price, price_date = None, None
        if confidence == "low" and source != "manual":
            flag("low confidence")

        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [round(place["lng"], 6), round(place["lat"], 6)]},
                "properties": {
                    "id": pid,
                    "name": place["name"],
                    "address": place["address"],
                    "score": round(score, 1),
                    "summary": rating.get("summary"),
                    "mentions": rating.get("mentions"),
                    "latest_mention": rating.get("latest_mention"),
                    "price": price,
                    "price_date": price_date,
                    "confidence": confidence,
                    "score_source": source,
                    "google_rating": place.get("rating"),
                    "google_rating_count": place.get("rating_count"),
                    "price_level": PRICE_LEVELS.get(place.get("price_level")),
                    "google_maps_url": place.get("google_maps_url"),
                    "website": place.get("website"),
                    "notes": override.get("note") or rating.get("notes"),
                },
            }
        )

    features.sort(key=lambda f: (-f["properties"]["score"], -(f["properties"]["mentions"] or 0)))
    config.GEOJSON_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.GEOJSON_FILE.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False, indent=1)
    )

    with config.REVIEW_FILE.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["place_id", "name", "score", "price", "reason", "summary", "notes"])
        writer.writeheader()
        writer.writerows(review)

    ok = [r for r in ratings.values() if r.get("status") == "ok"]
    print("Funnel")
    print(f"  discovered               {len(places)}")
    print(f"  with reviews             {sum(1 for r in reviews.values() if r)}")
    print(f"  sent to Claude           {len(ratings)}")
    print(f"  reviews discuss 滷肉飯   {sum(1 for r in ok if r.get('mentions'))}")
    print(f"  scored                   {sum(1 for r in ok if r.get('score') is not None)}")
    print(f"  on the map               {len(features)} ({sum(1 for f in features if f['properties']['price'])} with a price)")
    print(f"Wrote {config.GEOJSON_FILE.relative_to(config.ROOT)}; {len(review)} rows to review in "
          f"{config.REVIEW_FILE.relative_to(config.ROOT)}")


if __name__ == "__main__":
    main()
