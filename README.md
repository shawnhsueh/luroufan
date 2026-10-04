# 滷肉飯指數 — Taipei

**Live map: https://shawnhsueh.github.io/luroufan/**

Where is the 滷肉飯 (braised pork rice) good? This project reads the Google reviews of restaurants
in Taipei City, has Claude rate what reviewers say about the 滷肉飯, and plots the scores on an
interactive map (in Traditional Chinese).

A sibling of [calamari](https://github.com/shawnhsueh/calamari), which maps calamari prices in Vancouver.

```
Google Places (+ up to 5 reviews) ──► Claude rates the 滷肉飯 ──► GeoJSON ──► Leaflet map
        discover.py                        extract.py               build.py      web/
```

## Setup

```sh
conda create -n luroufan python=3.12 && conda activate luroufan
pip install -e '.[dev]'
cp .env.example .env   # add GOOGLE_MAPS_API_KEY (Places API (New) enabled) and ANTHROPIC_API_KEY
```

## Run

```sh
python -m pipeline.run                 # everything (rating runs as a Message Batch, ~<1h)
python -m pipeline.run --sync          # same, but rating one request at a time

# or step by step
python -m pipeline.discover --limit-cells 1   # try the centre grid cell first
python -m pipeline.extract --dry-run          # see what would be sent and roughly how many tokens
python -m pipeline.extract --sync --limit 10
python -m pipeline.build

python -m http.server -d web 8000             # open http://localhost:8000
```

Every step is cached and incremental: Places responses are cached in `data/cache/` (the cache key
includes the field mask), and a place is only re-sent to Claude when its reviews change. Use
`extract --force` to re-rate everything.

## How scores are made

- `discover` runs Places Text Search (`zh-TW`) over an 8×8 grid of Taipei City for 滷肉飯, 魯肉飯,
  小吃, 台式便當, 台菜餐廳 and 餐廳, keeps places whose municipality is 臺北市, and saves up to 5
  reviews per place to `data/reviews.jsonl`.
- `extract` sends a place to Claude (`claude-sonnet-5-5`, structured outputs) only if one of its
  reviews mentions *滷肉飯 / 魯肉飯 / 肉燥飯*. Claude judges only what reviewers say about the 滷肉飯
  (not service or other dishes) and returns a 1–5 **score**, a short Traditional Chinese **summary**,
  how many reviews discuss the dish, and any 滷肉飯 **price** a reviewer states, with that review's date.
  爌肉飯/控肉飯, 雞肉飯 and other rice bowls don't count.
- Confidence is low for a single mention, medium for two, high for three or more consistent ones.
- `build` maps every place with a score. Low-confidence scores and prices outside NT$20–200 are
  listed in `data/review.csv` (an out-of-range price is dropped, the place stays).

## Fixing data by hand

Edit `data/overrides.csv` and re-run `python -m pipeline.build`:

```csv
place_id,score,price,exclude,note
ChIJ...,4.5,35,,現場試吃 2026-10
ChIJ...,,,true,已歇業
```

An override needs the place to be in `data/restaurants.jsonl` (i.e. found by `discover`).

## Known gaps

- **Small samples.** The Places API returns at most 5 reviews per place, picked by Google as
  "most relevant", not the newest. Many scores rest on one or two reviews; the popup always says
  how many reviews mention the dish, and "隱藏低可信度評分" hides single-mention scores.
- Shops famous for something else (e.g. a noodle shop with a good 滷肉飯 on the side) may have no
  review among those 5 that mentions the 滷肉飯, so they're missing.
- Prices from reviews can be years old; the popup shows the review's month.
- Scores are Claude's reading of reviewers' opinions, not a taste test.

## Data use

Raw review text stays local (`data/reviews.jsonl` is gitignored). The published map only carries
Claude's score and summary, with "評論來源：Google" attribution and a link to each place's Google
Maps page.

## Updating the site

`web/` is a static site deployed to GitHub Pages by `.github/workflows/pages.yml` on every push
that touches `web/`. To refresh the data: re-run the pipeline, then commit and push
`web/data/restaurants.geojson`.

## Data & attribution

- Restaurant names and locations: Google Places API.
- Scores, summaries and prices: derived by Claude from Google reviews. Check the Google Maps page
  before you go.
- Basemap tiles: © Esri — Esri, HERE, Garmin, © OpenStreetMap contributors.

A personal, non-commercial project. Not affiliated with any of the restaurants listed.

## Tests

```sh
pytest
```
