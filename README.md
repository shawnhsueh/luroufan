# 滷肉飯指數 — Taipei

**Live map: https://shawnhsueh.github.io/luroufan/**

How pricey is a restaurant? 滷肉飯 (braised pork rice) is on nearly every 小吃 menu in Taipei, so its
price is a handy benchmark. This project finds the 滷肉飯 price at restaurants in Taipei City and
plots them on an interactive map (in Traditional Chinese, prices in NTD).

A sibling of [calamari](https://github.com/shawnhsueh/calamari), which does the same for calamari in Vancouver.

```
Google Places ──► restaurant websites ──► Claude reads the menu ──► GeoJSON ──► Leaflet map
 discover.py        fetch_menus.py            extract.py             build.py      web/
```

## Setup

```sh
conda create -n luroufan python=3.12 && conda activate luroufan
pip install -e '.[dev]'
cp .env.example .env   # add GOOGLE_MAPS_API_KEY (Places API (New) enabled) and ANTHROPIC_API_KEY
```

## Run

```sh
python -m pipeline.run                 # everything (extraction runs as a Message Batch, ~<1h)
python -m pipeline.run --sync          # same, but extraction one request at a time

# or step by step
python -m pipeline.discover --limit-cells 1   # try the centre grid cell first
python -m pipeline.fetch_menus --limit 20
python -m pipeline.extract --dry-run          # see what would be sent and roughly how many tokens
python -m pipeline.extract --sync --limit 10
python -m pipeline.build

python -m http.server -d web 8000             # open http://localhost:8000
```

Every step is cached and incremental: Places responses are cached in `data/cache/`, crawled
menus live in `data/menus/<place_id>/`, and a menu is only re-sent to Claude when its content
changes. Use `fetch_menus --refresh` to re-crawl and `extract --force` to re-extract.

## How prices are chosen

- `discover` runs Places Text Search (`zh-TW`) over an 8×8 grid of Taipei City for 滷肉飯, 魯肉飯,
  小吃, 台式便當, 台菜餐廳 and 餐廳, and keeps places whose municipality is 臺北市.
- `fetch_menus` finds menu pages, PDFs, embedded menus (iframes) and menu images on each site.
  Only restaurants whose menus mention *滷肉飯 / 魯肉飯 / 肉燥飯*, or that only have scanned/image
  menus, are sent to Claude (`claude-sonnet-5-5`, structured outputs).
- The **benchmark price** is the à-la-carte 滷肉飯, smallest bowl (小碗), never a 套餐/便當 price.
  爌肉飯/控肉飯, 雞肉飯 and other rice bowls don't count. All matching items found are kept and shown
  in the popup.
- `build` keeps prices between NT$20 and NT$200; anything else, plus low-confidence reads, goes
  to `data/review.csv`.

## Fixing data by hand

Edit `data/overrides.csv` and re-run `python -m pipeline.build`:

```csv
place_id,benchmark_price,dish_name,exclude,note
ChIJ...,35,滷肉飯(小),,現場確認 2026-10
ChIJ...,,,true,已歇業
```

An override needs the place to be in `data/restaurants.jsonl` (i.e. found by `discover`).

## Known gaps

- **Most 小吃 shops have no crawlable website.** Many list nothing, and many list a Facebook,
  Instagram or LINE page as their website (`social_only` in `data/menu_status.jsonl`), which
  can't be read without logging in. So the map leans toward chains and sit-down restaurants with
  real websites, and the classic 滷肉飯 stalls are under-represented. Manual overrides are the
  way to add them.
- Menus that need JavaScript to render, or sites that block crawlers, end up as
  `menu_not_found` / `fetch_failed`.
- Chains often post one menu for all locations, so every location shows the same price.
- Google photos were considered as a second source (menu boards), but rejected: the Places API
  doesn't mark menu photos or date them, and downloading ~10 photos per shop costs ~$7/1,000.

## Updating the site

`web/` is a static site deployed to GitHub Pages by `.github/workflows/pages.yml` on every push
that touches `web/`. To refresh the data: re-run the pipeline, then commit and push
`web/data/restaurants.geojson`.

## Data & attribution

- Restaurant names and locations: Google Places API.
- 滷肉飯 prices: read from each restaurant's own website/menus. Prices change; check the linked
  menu before you go.
- Basemap tiles: © Esri — Esri, HERE, Garmin, © OpenStreetMap contributors.

A personal, non-commercial project. Not affiliated with any of the restaurants listed.

## Tests

```sh
pytest
```
