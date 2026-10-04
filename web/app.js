"use strict";

const TAIPEI = [25.0375, 121.5637];
const BINS = 5;
const dark = window.matchMedia("(prefers-color-scheme: dark)");
const css = getComputedStyle(document.querySelector(".viz-root"));
const binColor = (i) => css.getPropertyValue(`--bin-${i + 1}`).trim();
const ringColor = () => css.getPropertyValue("--ring").trim();
const money = (v) => (v == null ? "–" : `NT$${Math.round(v)}`);
const stars = (v) => (v == null ? "–" : `★${Number(v).toFixed(1)}`);
const CONFIDENCE = { low: "低", medium: "中" };
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);

const map = L.map("map", { zoomControl: true }).setView(TAIPEI, 13);
// Esri's neutral gray canvas: no API key, and gray keeps the blue ramp readable.
const tileUrl = () =>
  `https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_${dark.matches ? "Dark" : "Light"}_Gray_Base/MapServer/tile/{z}/{y}/{x}`;
const tiles = L.tileLayer(tileUrl(), {
  maxZoom: 19,
  maxNativeZoom: 16,
  attribution: 'Tiles &copy; <a href="https://www.esri.com">Esri</a> &mdash; Esri, HERE, Garmin, &copy; OpenStreetMap contributors &middot; 評論來源：Google',
}).addTo(map);

let features = [];
let breaks = []; // upper bound of each bin except the last
const markers = new Map(); // id -> circle marker

// Quantile breaks over the full dataset, so filtering never repaints a restaurant.
function quantileBreaks(values) {
  const sorted = [...values].sort((a, b) => a - b);
  const out = [];
  for (let i = 1; i < BINS; i++) out.push(sorted[Math.floor((i / BINS) * (sorted.length - 1))]);
  return out;
}
const binOf = (score) => {
  const i = breaks.findIndex((b) => score <= b);
  return i === -1 ? BINS - 1 : i;
};

function median(values) {
  if (!values.length) return null;
  const s = [...values].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

function popupHtml(p) {
  const conf = p.confidence && p.confidence !== "high" ? ` <span class="badge">可信度${esc(CONFIDENCE[p.confidence] || p.confidence)}</span>` : "";
  const mentions = p.score_source === "manual"
    ? "手動輸入"
    : `${p.mentions ?? 0} 則評論提到滷肉飯${p.latest_mention ? ` · 最近 ${esc(p.latest_mention.slice(0, 7))}` : ""}`;
  const price = p.price ? `<div class="meta">滷肉飯 ${money(p.price)}${p.price_date ? `（評論，${esc(p.price_date.slice(0, 7))}）` : ""}</div>` : "";
  const google = p.google_rating ? `Google 整體評分 ${Number(p.google_rating).toFixed(1)}${p.google_rating_count ? `（${p.google_rating_count.toLocaleString()} 則）` : ""}` : "";
  const level = p.price_level ? ` · 價位 ${"$".repeat(p.price_level)}` : "";
  return `<div class="popup">
    <h3>${esc(p.name)}</h3>
    <div class="addr">${esc(p.address)}</div>
    <div><span class="big">${stars(p.score)}</span>${conf}</div>
    ${p.summary ? `<div class="summary">${esc(p.summary)}</div>` : ""}
    <div class="meta">${mentions}</div>
    ${price}
    ${p.notes ? `<div class="meta">${esc(p.notes)}</div>` : ""}
    ${google ? `<div class="meta">${google}${level}</div>` : ""}
    <div class="links">
      ${p.google_maps_url ? `<a href="${esc(p.google_maps_url)}" target="_blank" rel="noopener">Google 地圖評論</a>` : ""}
      ${p.website ? `<a href="${esc(p.website)}" target="_blank" rel="noopener">網站</a>` : ""}
    </div>
  </div>`;
}

function markerStyle(p) {
  return { radius: 7, weight: 2, color: ringColor(), fillColor: binColor(binOf(p.score)), fillOpacity: 1 };
}

function buildMarkers() {
  for (const f of features) {
    const p = f.properties;
    const [lng, lat] = f.geometry.coordinates;
    const m = L.circleMarker([lat, lng], markerStyle(p))
      .bindTooltip(`<strong>${esc(p.name)}</strong> · ${stars(p.score)}`, { direction: "top", offset: [0, -6] })
      .bindPopup(popupHtml(p), { maxWidth: 300 });
    m.on("mouseover", () => m.setStyle({ radius: 9 }));
    m.on("mouseout", () => m.setStyle({ radius: 7 }));
    markers.set(p.id, m);
  }
}

function renderLegend() {
  const scores = features.map((f) => f.properties.score);
  const edges = [Math.min(...scores), ...breaks, Math.max(...scores)];
  const fmt = (v) => Number(v).toFixed(1);
  document.getElementById("legend-bins").innerHTML = Array.from({ length: BINS }, (_, i) => {
    const label = i === 0 ? `≤ ${fmt(edges[1])}` : i === BINS - 1 ? `> ${fmt(edges[i])}` : `${fmt(edges[i])}–${fmt(edges[i + 1])}`;
    return `<li><span class="swatch" style="background:${binColor(i)}"></span>${label}</li>`;
  }).join("");
}

const els = {
  search: document.getElementById("search"),
  min: document.getElementById("score-min"),
  hideLow: document.getElementById("hide-low"),
  pricedOnly: document.getElementById("priced-only"),
  scoreLabel: document.getElementById("score-label"),
  list: document.getElementById("list"),
  listCount: document.getElementById("list-count"),
};

function applyFilters() {
  const lo = Number(els.min.value);
  els.scoreLabel.textContent = `${stars(lo)} 以上`;
  const q = els.search.value.trim().toLowerCase();

  const visible = features.filter(({ properties: p }) =>
    p.score >= lo &&
    !(els.hideLow.checked && p.confidence === "low") &&
    !(els.pricedOnly.checked && !p.price) &&
    (!q || p.name.toLowerCase().includes(q))
  );
  const ids = new Set(visible.map((f) => f.properties.id));
  for (const [id, m] of markers) {
    if (ids.has(id)) m.addTo(map);
    else m.remove();
  }

  const scores = visible.map((f) => f.properties.score);
  const prices = visible.map((f) => f.properties.price).filter((v) => v);
  document.getElementById("stat-count").textContent = visible.length;
  document.getElementById("stat-avg").textContent = scores.length ? stars(scores.reduce((a, b) => a + b, 0) / scores.length) : "–";
  document.getElementById("stat-top").textContent = scores.length ? stars(Math.max(...scores)) : "–";
  document.getElementById("stat-price").textContent = money(median(prices));

  els.listCount.textContent = `（${visible.length}）`;
  els.list.innerHTML = visible.length
    ? visible
        .map(({ properties: p }) => `<li><button data-id="${esc(p.id)}">
          <span class="dot" style="background:${binColor(binOf(p.score))}"></span>
          <span class="name">${esc(p.name)}</span>
          <span class="price">${stars(p.score)}</span></button></li>`)
        .join("")
    : `<li class="empty">沒有符合條件的餐廳。</li>`;
}

els.list.addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-id]");
  if (!btn) return;
  const m = markers.get(btn.dataset.id);
  map.flyTo(m.getLatLng(), Math.max(map.getZoom(), 16), { duration: 0.6 });
  m.openPopup();
});
for (const el of [els.search, els.min, els.hideLow, els.pricedOnly]) el.addEventListener("input", applyFilters);

// Follow OS theme changes: swap tiles and recolor from the new CSS variables.
dark.addEventListener("change", () => {
  tiles.setUrl(tileUrl());
  for (const f of features) markers.get(f.properties.id).setStyle(markerStyle(f.properties));
  renderLegend();
  applyFilters();
});

async function init() {
  let data;
  try {
    const resp = await fetch("data/restaurants.geojson", { cache: "no-cache" });
    if (!resp.ok) throw new Error(resp.status);
    data = await resp.json();
  } catch {
    data = { features: [] };
  }
  features = (data.features || []).filter((f) => typeof f.properties.score === "number");
  if (!features.length) {
    els.list.innerHTML = `<li class="empty">尚無資料。請執行 <code>python -m pipeline.run</code> 產生資料。</li>`;
    return;
  }
  breaks = quantileBreaks(features.map((f) => f.properties.score));

  buildMarkers();
  renderLegend();
  applyFilters();
  map.fitBounds(L.featureGroup([...markers.values()]).getBounds(), { padding: [30, 30], maxZoom: 15 });
}

init();
