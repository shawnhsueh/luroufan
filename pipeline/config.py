"""Shared settings and paths for the 滷肉飯 (braised pork rice) pipeline."""

import json
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
MENUS_DIR = DATA_DIR / "menus"
RESTAURANTS_FILE = DATA_DIR / "restaurants.jsonl"
MENU_STATUS_FILE = DATA_DIR / "menu_status.jsonl"
PRICES_FILE = DATA_DIR / "prices.jsonl"
OVERRIDES_FILE = DATA_DIR / "overrides.csv"
BATCH_STATE_FILE = DATA_DIR / "batch_state.json"
REVIEW_FILE = DATA_DIR / "review.csv"
GEOJSON_FILE = ROOT / "web" / "data" / "restaurants.geojson"

# Taipei City bounding box (south, west, north, east). Places in New Taipei and
# other neighbours are dropped later by the locality filter.
BBOX = (24.960, 121.457, 25.210, 121.666)
GRID_ROWS = 8
GRID_COLS = 8

SEARCH_QUERIES = [
    "滷肉飯",
    "魯肉飯",
    "小吃",
    "台式便當",
    "台菜餐廳",
    "餐廳",
]
# 臺北市 is a special municipality, so Google reports it as administrative_area_level_1.
ALLOWED_LOCALITIES = {"臺北市", "台北市", "Taipei City"}
LANGUAGE_CODE = "zh-TW"
REGION_CODE = "TW"

PLACES_FIELDS = ",".join(
    "places." + f
    for f in [
        "id",
        "displayName",
        "location",
        "websiteUri",
        "formattedAddress",
        "addressComponents",
        "priceLevel",
        "rating",
        "userRatingCount",
        "primaryType",
        "googleMapsUri",
        "businessStatus",
    ]
) + ",nextPageToken"

MODEL = "claude-sonnet-5-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"

# Benchmark prices outside this range are kept out of the map and flagged for review.
PRICE_MIN, PRICE_MAX = 20, 200  # NTD

DISH_PATTERN = r"滷肉飯|魯肉飯|肉燥飯|滷肉|魯肉|braised pork rice|lu ?rou"

# Many restaurant sites (behind Cloudflare etc.) refuse unfamiliar bot user-agents.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36 LurouIndex/0.1"
)


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"Missing {name}. Copy .env.example to .env and fill it in.")
    return value


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open() as f:
        return [json.loads(line) for line in f if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
