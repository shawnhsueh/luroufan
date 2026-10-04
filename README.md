# 滷肉飯指數 — 台北

**線上地圖：https://shawnhsueh.github.io/luroufan/**

台北哪裡的滷肉飯好吃？這個專案讀取台北市餐廳的 Google 評論，由 Claude 依據評論中關於滷肉飯的內容評分，
再把結果畫在互動地圖上。

姊妹專案：[calamari](https://github.com/shawnhsueh/calamari)（溫哥華炸魷魚價格地圖）。

```
Google Places（每家最多 5 則評論）──► Claude 為滷肉飯評分 ──► GeoJSON ──► Leaflet 地圖
        discover.py                       extract.py             build.py      web/
```

## 安裝

```sh
conda create -n luroufan python=3.12 && conda activate luroufan
pip install -e '.[dev]'
cp .env.example .env   # 填入 GOOGLE_MAPS_API_KEY（需啟用 Places API (New)）和 ANTHROPIC_API_KEY
```

## 執行

```sh
python -m pipeline.run                 # 全部流程（評分以 Message Batch 送出，通常一小時內完成）
python -m pipeline.run --sync          # 同上，但評分改為逐筆送出

# 或分步驟執行
python -m pipeline.discover --limit-cells 1   # 先只搜尋中央的一格試試
python -m pipeline.extract --dry-run          # 預覽會送出的內容和大約的 token 數
python -m pipeline.extract --sync --limit 10
python -m pipeline.build

python -m http.server -d web 8000             # 開啟 http://localhost:8000
```

每個步驟都有快取、可增量執行：Places 的回應快取在 `data/cache/`（快取鍵包含欄位遮罩），
店家的評論有變動時才會重新送給 Claude 評分。用 `extract --force` 可以全部重新評分。

## 評分方式

- `discover` 以 `zh-TW` 對台北市 8×8 的網格執行 Places 文字搜尋，關鍵字為滷肉飯、魯肉飯、小吃、
  台式便當、台菜餐廳和餐廳。只保留地址在臺北市的店家，並把每家最多 5 則評論存到 `data/reviews.jsonl`。
- `extract` 只把評論中提到「滷肉飯／魯肉飯／肉燥飯」的店家送給 Claude（`claude-sonnet-5-5`，結構化輸出）。
  Claude 只看評論對滷肉飯本身的描述（不看服務或其他菜色），產出 1–5 分的**評分**、一句繁體中文**摘要**、
  提到滷肉飯的評論數，以及評論中提到的滷肉飯**價格**和該則評論的日期。
  爌肉飯／控肉飯、雞肉飯等其他飯類不列入。
- 可信度：只有一則評論提到為「低」，兩則一致為「中」，三則以上一致為「高」。
- `build` 把所有有評分的店家放上地圖。低可信度的評分，以及超出 NT$20–200 的價格，會列在
  `data/review.csv`（超出範圍的價格會被移除，但店家仍保留在地圖上）。

## 手動修正資料

編輯 `data/overrides.csv`，再重新執行 `python -m pipeline.build`：

```csv
place_id,score,price,exclude,note
ChIJ...,4.5,35,,現場試吃 2026-10
ChIJ...,,,true,已歇業
```

要修正的店家必須已在 `data/restaurants.jsonl` 中（也就是 `discover` 有找到）。

## 已知限制

- **樣本很小。** Places API 每家店最多只回傳 5 則評論，由 Google 挑選「最相關」的，而不是最新的。
  很多評分只根據一、兩則評論；彈出視窗一定會顯示有幾則評論提到滷肉飯，勾選「隱藏低可信度評分」
  可以隱藏只有一則評論的評分。
- 以其他料理出名的店（例如滷肉飯是配角的麵店），這 5 則評論可能都沒提到滷肉飯，因此不會出現在地圖上。
- 評論中的價格可能是好幾年前的；彈出視窗會顯示評論的年月。
- 評分是 Claude 對評論者意見的解讀，不是實際試吃。

## 資料使用

評論原文只存在本機（`data/reviews.jsonl` 不納入 git）。公開的地圖只包含 Claude 產生的評分和摘要，
並標示「評論來源：Google」，附上各店家的 Google 地圖連結。

## 更新網站

`web/` 是靜態網站，每次推送有變動 `web/` 的 commit 時，由 `.github/workflows/pages.yml` 部署到
GitHub Pages。要更新資料：重新執行流程，再 commit 並推送 `web/data/restaurants.geojson`。

## 資料來源與標示

- 店名與位置：Google Places API。
- 評分、摘要與價格：由 Claude 根據 Google 評論產生。前往前請先查看 Google 地圖頁面。
- 底圖：© Esri — Esri, HERE, Garmin, © OpenStreetMap contributors。

個人非商業專案，與地圖上的任何餐廳均無關係。

## 測試

```sh
pytest
```
