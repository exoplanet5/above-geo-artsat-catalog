// Above-GEO Artsat catalog - Plotly frontend
// Three cross-linked Plotly views over the same dataset:
//   1. Perigee vs Apogee (log-log)
//   2. RAAN Omega vs Inclination
//   3. 3D Perigee x Apogee x Inclination orbit explorer
// Plus a stacked period histogram by apogee zone.

const PLOTS = {
  periApo: "plotPeriApo",
  raanInc: "plotRaanInc",
  three: "plot3d",
  hist:  "plotHist",
};

// Apogee-band zones above GEO. Bill Gray's extended-format TLEs are
// already deep-space by construction so they get their own bucket.
const ZONE_COLORS = {
  "xGEO":       "#f4a23a",  // 36k - 100k km apogee
  "cislunar":   "#61dafb",  // 100k - 400k km apogee
  "translunar": "#ffe189",  // >= 400k km (lunar+ heliocentric)
  "deep-space": "#b34784",  // extended-format TLEs (no parsed elements)
  "unknown":    "#56606b",
};

const ZONE_ORDER = ["xGEO", "cislunar", "translunar", "deep-space", "unknown"];

const NUMERIC_KEYS = new Set([
  "norad_id", "raan_deg", "inclination_deg",
  "period_day", "perigee_km", "apogee_km",
]);

const state = {
  dataset: null,
  filtered: [],
  sort: { key: "period_day", dir: "desc" },
  enabledZones: new Set(ZONE_ORDER),
  highlightId: null,
  suspendHover: false,
};

const LAYOUT_BASE = {
  paper_bgcolor: "rgba(0,0,0,0)",
  plot_bgcolor:  "rgba(7,12,19,0.55)",
  font: { color: "#dfe5e8", family: "Menlo, Consolas, monospace", size: 11 },
  margin: { l: 64, r: 18, t: 32, b: 50 },
  hoverlabel: {
    bgcolor: "#101824",
    bordercolor: "#ffcb77",
    font: { color: "#f6f6ee", family: "Menlo, monospace", size: 11 },
  },
};

const CONFIG_2D = {
  displaylogo: false,
  responsive: true,
  modeBarButtonsToRemove: ["lasso2d", "select2d", "autoScale2d", "toggleSpikelines"],
};

const CONFIG_3D = {
  displaylogo: false,
  responsive: true,
};

// ---------- Data load ------------------------------------------------------

async function loadDataset() {
  // /api/orbits is served by serve.py locally; ./data/orbits.json is the
  // layout used by HF Spaces (data/ next to index.html in the deploy bundle);
  // ../data/orbits.json supports the dev tree where web/ and data/ are siblings.
  const candidates = ["/api/orbits", "./data/orbits.json", "../data/orbits.json"];
  let lastErr = null;
  for (const url of candidates) {
    try {
      const r = await fetch(url);
      if (!r.ok) throw new Error(`HTTP ${r.status} at ${url}`);
      return await r.json();
    } catch (e) {
      lastErr = e;
    }
  }
  throw lastErr || new Error("Failed to load orbits.json");
}

const numOrNull = (v) => (typeof v === "number" && Number.isFinite(v) ? v : null);
const fmt = (v, d = 3) =>
  typeof v === "number" && Number.isFinite(v) ? v.toFixed(d) : "-";

// ---------- Filtering ------------------------------------------------------

function readNumber(id) {
  const raw = document.getElementById(id).value.trim();
  if (!raw) return null;
  const v = Number(raw);
  return Number.isFinite(v) ? v : null;
}

function inRange(v, lo, hi) {
  if (lo === null && hi === null) return true;
  if (v === null) return false;
  if (lo !== null && v < lo) return false;
  if (hi !== null && v > hi) return false;
  return true;
}

function applyFilters() {
  if (!state.dataset) return;
  const search = document.getElementById("searchInput").value.trim().toLowerCase();
  const incExt = document.getElementById("includeExtended").checked;

  const f = {
    raan: [readNumber("raanMin"), readNumber("raanMax")],
    inc:  [readNumber("incMin"),  readNumber("incMax")],
    per:  [readNumber("periodMin"), readNumber("periodMax")],
    peri: [readNumber("perigeeMin"), readNumber("perigeeMax")],
    apo:  [readNumber("apogeeMin"),  readNumber("apogeeMax")],
  };

  state.filtered = state.dataset.satellites.filter((s) => {
    if (!incExt && s.is_extended_format) return false;
    if (!state.enabledZones.has(s.zone)) return false;
    if (search) {
      const hay = [s.name, s.norad_id, s.cospar_id, s.include_file, s.zone]
        .join(" ").toLowerCase();
      if (!hay.includes(search)) return false;
    }
    if (!inRange(numOrNull(s.raan_deg),       f.raan[0], f.raan[1])) return false;
    if (!inRange(numOrNull(s.inclination_deg), f.inc[0],  f.inc[1]))  return false;
    if (!inRange(numOrNull(s.period_day),      f.per[0],  f.per[1]))  return false;
    if (!inRange(numOrNull(s.perigee_km),      f.peri[0], f.peri[1])) return false;
    if (!inRange(numOrNull(s.apogee_km),       f.apo[0],  f.apo[1]))  return false;
    return true;
  });

  state.highlightId = null;
  renderStats();
  renderTable();
  redrawAllPlots();
}

// ---------- Stats ----------------------------------------------------------

function renderStats() {
  const total = state.filtered.length;
  const classical = state.filtered.filter((s) => s.is_extended_format === false).length;
  const ext = state.filtered.filter((s) => s.is_extended_format === true).length;
  const xgeo = state.filtered.filter((s) => s.zone === "xGEO").length;
  const cislunar = state.filtered.filter((s) => s.zone === "cislunar").length;
  const translunar = state.filtered.filter((s) => s.zone === "translunar").length;

  const cards = [
    { label: "Filtered Entries",     value: total },
    { label: "Classical Elements",   value: classical },
    { label: "xGEO",                 value: xgeo },
    { label: "Cislunar",             value: cislunar },
    { label: "Translunar",           value: translunar },
    { label: "Deep-Space (Extended)", value: ext },
  ];

  document.getElementById("stats").innerHTML = cards
    .map((c) => `
      <article class="stat">
        <div class="stat-label">${c.label}</div>
        <div class="stat-value">${c.value}</div>
      </article>`)
    .join("");
}

// ---------- Sortable table -------------------------------------------------

function sortValue(row, key) {
  if (key === "is_extended_format") return row.is_extended_format ? "extended" : "classical";
  if (key === "zone") {
    const idx = ZONE_ORDER.indexOf(row.zone);
    return idx === -1 ? ZONE_ORDER.length : idx;
  }
  const v = row[key];
  if (v === null || v === undefined) return null;
  if (NUMERIC_KEYS.has(key)) return Number(v);
  return String(v).toLowerCase();
}

function sortRows(rows) {
  const k = state.sort.key;
  const f = state.sort.dir === "asc" ? 1 : -1;
  rows.sort((a, b) => {
    const av = sortValue(a, k);
    const bv = sortValue(b, k);
    if (av === null && bv === null) return 0;
    if (av === null) return 1;
    if (bv === null) return -1;
    if (typeof av === "number" && typeof bv === "number") return (av - bv) * f;
    if (av < bv) return -1 * f;
    if (av > bv) return 1 * f;
    return 0;
  });
  return rows;
}

function renderTable() {
  const tbody = document.querySelector("#satTable tbody");
  const rows = sortRows(state.filtered.slice()).slice(0, 1500);
  const hl = state.highlightId;

  document.getElementById("tableCount").textContent =
    `${state.filtered.length} entries (showing ${rows.length})`;

  tbody.innerHTML = rows.map((s) => {
    const zoneColor = ZONE_COLORS[s.zone] || ZONE_COLORS.unknown;
    return `
      <tr data-id="${s.id}" class="${s.id === hl ? "row-highlight" : ""}">
        <td>${s.name || "-"}</td>
        <td>${s.norad_id ?? "-"}</td>
        <td>${s.cospar_id ?? "-"}</td>
        <td><span class="fam-badge" style="color:${zoneColor};border-color:${zoneColor}66">${s.zone}</span></td>
        <td>${s.include_file}</td>
        <td>${s.tle_epoch_utc || "-"}</td>
        <td>${fmt(s.raan_deg, 3)}</td>
        <td>${fmt(s.inclination_deg, 3)}</td>
        <td>${fmt(s.period_day, 4)}</td>
        <td>${fmt(s.perigee_km, 1)}</td>
        <td>${fmt(s.apogee_km, 1)}</td>
        <td>${s.is_extended_format ? "Extended" : "Classical"}</td>
      </tr>`;
  }).join("");

  // Click row -> highlight everywhere
  tbody.querySelectorAll("tr").forEach((tr) => {
    tr.addEventListener("click", () => {
      const id = Number(tr.dataset.id);
      setHighlight(id);
    });
  });
}

function highlightTableRow(id, scroll = false) {
  document.querySelectorAll("#satTable tbody tr").forEach((tr) => {
    if (Number(tr.dataset.id) === id) {
      tr.classList.add("row-highlight");
      if (scroll) tr.scrollIntoView({ block: "nearest" });
    } else {
      tr.classList.remove("row-highlight");
    }
  });
}

function updateSortIndicators() {
  document.querySelectorAll(".th-sort").forEach((b) => {
    const k = b.dataset.key;
    const ind = b.querySelector(".ind");
    const active = k === state.sort.key;
    if (ind) ind.textContent = active ? (state.sort.dir === "asc" ? "\u25B2" : "\u25BC") : "\u2195";
    b.setAttribute("aria-sort",
      active ? (state.sort.dir === "asc" ? "ascending" : "descending") : "none");
  });
}

function setupSorting() {
  document.querySelectorAll(".th-sort").forEach((b) => {
    b.addEventListener("click", () => {
      const k = b.dataset.key;
      if (!k) return;
      if (state.sort.key === k) {
        state.sort.dir = state.sort.dir === "asc" ? "desc" : "asc";
      } else {
        state.sort.key = k;
        state.sort.dir = NUMERIC_KEYS.has(k) ? "desc" : "asc";
      }
      renderTable();
      updateSortIndicators();
    });
  });
  updateSortIndicators();
}

// ---------- Plotly traces --------------------------------------------------

function classicalRows() {
  return state.filtered.filter((s) =>
    Number.isFinite(s.perigee_km) && Number.isFinite(s.apogee_km)
    && Number.isFinite(s.inclination_deg) && Number.isFinite(s.raan_deg)
    && Number.isFinite(s.period_day));
}

function buildHover(s) {
  const lines = [
    `<b>${s.name || s.include_file || "Unnamed"}</b>`,
    `NORAD: ${s.norad_id ?? "-"}  COSPAR: ${s.cospar_id ?? "-"}`,
    `Zone: ${s.zone}`,
    `RAAN \u03A9: ${fmt(s.raan_deg, 3)}\u00B0`,
    `Inclination i: ${fmt(s.inclination_deg, 3)}\u00B0`,
    `Period: ${fmt(s.period_day, 4)} day`,
    `Perigee: ${fmt(s.perigee_km, 1)} km`,
    `Apogee: ${fmt(s.apogee_km, 1)} km`,
  ];
  return lines.join("<br>");
}

function periApoTrace(rows) {
  const ids = rows.map((s) => s.id);
  return [{
    type: "scattergl",
    mode: "markers",
    x: rows.map((s) => s.perigee_km),
    y: rows.map((s) => s.apogee_km),
    customdata: ids,
    text: rows.map(buildHover),
    hovertemplate: "%{text}<extra></extra>",
    marker: {
      size: 8,
      color: rows.map((s) => s.inclination_deg),
      colorscale: "Viridis",
      cmin: 0,
      cmax: 180,
      showscale: true,
      colorbar: {
        title: { text: "Inc (deg)", font: { size: 11 } },
        thickness: 12,
        x: 1.02,
      },
      line: { width: 0.5, color: "rgba(255,255,255,0.25)" },
    },
  }, {
    // Highlight overlay (single point, updated via Plotly.restyle)
    type: "scattergl",
    mode: "markers",
    x: [], y: [], customdata: [],
    hoverinfo: "skip",
    showlegend: false,
    marker: {
      size: 18,
      color: "rgba(255,225,137,0)",
      line: { width: 3, color: "#ffe189" },
    },
  }];
}

function raanIncTrace(rows) {
  const ids = rows.map((s) => s.id);
  const periodLog = rows.map((s) => Math.log10(Math.max(s.period_day, 0.001)));
  return [{
    type: "scattergl",
    mode: "markers",
    x: rows.map((s) => s.raan_deg),
    y: rows.map((s) => s.inclination_deg),
    customdata: ids,
    text: rows.map(buildHover),
    hovertemplate: "%{text}<extra></extra>",
    marker: {
      size: 8,
      color: periodLog,
      colorscale: "Plasma",
      showscale: true,
      colorbar: {
        title: { text: "log10 Period (day)", font: { size: 11 } },
        thickness: 12,
        x: 1.02,
      },
      line: { width: 0.5, color: "rgba(255,255,255,0.25)" },
    },
  }, {
    type: "scattergl",
    mode: "markers",
    x: [], y: [], customdata: [],
    hoverinfo: "skip",
    showlegend: false,
    marker: {
      size: 18,
      color: "rgba(255,225,137,0)",
      line: { width: 3, color: "#ffe189" },
    },
  }];
}

function threeDTraces(rows) {
  // One trace per zone so the legend is meaningful and clicks toggle them.
  const byZone = new Map();
  for (const s of rows) {
    const key = s.zone || "unknown";
    if (!byZone.has(key)) byZone.set(key, []);
    byZone.get(key).push(s);
  }
  const traces = [];
  for (const zone of ZONE_ORDER) {
    const list = byZone.get(zone);
    if (!list || !list.length) continue;
    traces.push({
      type: "scatter3d",
      mode: "markers",
      name: `${zone} (${list.length})`,
      legendgroup: zone,
      x: list.map((s) => s.perigee_km),
      y: list.map((s) => s.apogee_km),
      z: list.map((s) => s.inclination_deg),
      customdata: list.map((s) => s.id),
      text: list.map(buildHover),
      hovertemplate: "%{text}<extra></extra>",
      marker: {
        size: 4.5,
        color: ZONE_COLORS[zone] || ZONE_COLORS.unknown,
        opacity: 0.92,
        line: { width: 0.5, color: "rgba(255,255,255,0.18)" },
      },
    });
  }
  // Highlight overlay trace (always last)
  traces.push({
    type: "scatter3d",
    mode: "markers",
    name: "selected",
    showlegend: false,
    x: [], y: [], z: [], customdata: [],
    hoverinfo: "skip",
    marker: {
      size: 11,
      color: "rgba(255,225,137,0.0)",
      line: { width: 4, color: "#ffe189" },
    },
  });
  return traces;
}

function histogramTraces(rows) {
  // Stacked log-period histogram, one trace per zone.
  const traces = [];
  for (const zone of ZONE_ORDER) {
    const fr = rows.filter((s) => s.zone === zone
      && Number.isFinite(s.period_day) && s.period_day > 0);
    if (!fr.length) continue;
    traces.push({
      type: "histogram",
      x: fr.map((s) => Math.log10(s.period_day)),
      name: zone,
      marker: {
        color: ZONE_COLORS[zone] || ZONE_COLORS.unknown,
        line: { width: 0.3, color: "#000" },
      },
      opacity: 0.92,
      xbins: { start: -0.4, end: 2.6, size: 0.08 },
    });
  }
  return traces;
}

// ---------- Layouts --------------------------------------------------------

function layoutPeriApo() {
  return {
    ...LAYOUT_BASE,
    height: 460,
    xaxis: {
      title: { text: "Perigee (km)" },
      type: "log",
      gridcolor: "rgba(255,255,255,0.07)",
      zerolinecolor: "rgba(255,255,255,0.15)",
    },
    yaxis: {
      title: { text: "Apogee (km)" },
      type: "log",
      gridcolor: "rgba(255,255,255,0.07)",
      zerolinecolor: "rgba(255,255,255,0.15)",
    },
    showlegend: false,
  };
}

function layoutRaanInc() {
  return {
    ...LAYOUT_BASE,
    height: 460,
    xaxis: {
      title: { text: "RAAN \u03A9 (deg)" },
      range: [0, 360],
      gridcolor: "rgba(255,255,255,0.07)",
    },
    yaxis: {
      title: { text: "Inclination i (deg)" },
      range: [0, 180],
      gridcolor: "rgba(255,255,255,0.07)",
    },
    showlegend: false,
  };
}

function layout3d() {
  return {
    ...LAYOUT_BASE,
    height: 600,
    margin: { l: 0, r: 0, t: 20, b: 0 },
    scene: {
      xaxis: {
        title: "Perigee (km)", type: "log",
        backgroundcolor: "rgba(7,12,19,0.6)",
        gridcolor: "rgba(255,255,255,0.12)",
        zerolinecolor: "rgba(255,255,255,0.2)",
        color: "#dfe5e8",
      },
      yaxis: {
        title: "Apogee (km)", type: "log",
        backgroundcolor: "rgba(7,12,19,0.6)",
        gridcolor: "rgba(255,255,255,0.12)",
        zerolinecolor: "rgba(255,255,255,0.2)",
        color: "#dfe5e8",
      },
      zaxis: {
        title: "Inclination (deg)",
        backgroundcolor: "rgba(7,12,19,0.6)",
        gridcolor: "rgba(255,255,255,0.12)",
        zerolinecolor: "rgba(255,255,255,0.2)",
        color: "#dfe5e8",
      },
      camera: { eye: { x: 1.6, y: 1.5, z: 1.0 } },
    },
    legend: {
      x: 0.01, y: 0.99,
      bgcolor: "rgba(8,12,18,0.7)",
      bordercolor: "rgba(255,255,255,0.2)",
      borderwidth: 1,
      font: { size: 11 },
    },
  };
}

function layoutHist() {
  return {
    ...LAYOUT_BASE,
    height: 320,
    barmode: "stack",
    xaxis: {
      title: { text: "log10 Period (day)" },
      gridcolor: "rgba(255,255,255,0.07)",
    },
    yaxis: {
      title: { text: "Count" },
      gridcolor: "rgba(255,255,255,0.07)",
    },
    legend: {
      orientation: "h",
      y: 1.12, x: 0,
      font: { size: 10 },
    },
    margin: { l: 64, r: 18, t: 30, b: 50 },
  };
}

// ---------- Plot lifecycle -------------------------------------------------

function redrawAllPlots() {
  const rows = classicalRows();
  document.getElementById("periApoCount").textContent = `${rows.length} pts`;
  document.getElementById("raanIncCount").textContent = `${rows.length} pts`;

  Plotly.react(PLOTS.periApo, periApoTrace(rows), layoutPeriApo(), CONFIG_2D);
  Plotly.react(PLOTS.raanInc, raanIncTrace(rows), layoutRaanInc(), CONFIG_2D);
  Plotly.react(PLOTS.three,   threeDTraces(rows), layout3d(),    CONFIG_3D);
  Plotly.react(PLOTS.hist,    histogramTraces(rows), layoutHist(), CONFIG_2D);

  bindHoverHandlers();
}

let handlersBound = false;
function bindHoverHandlers() {
  if (handlersBound) return;
  handlersBound = true;
  for (const id of [PLOTS.periApo, PLOTS.raanInc, PLOTS.three]) {
    const el = document.getElementById(id);
    el.on("plotly_hover", (ev) => {
      if (state.suspendHover) return;
      const pt = ev.points && ev.points[0];
      if (!pt) return;
      const satId = Array.isArray(pt.customdata) ? pt.customdata[0] : pt.customdata;
      if (typeof satId !== "number") return;
      // Hover just paints the overlay + row class; no scroll-to-row.
      setHighlight(satId, id, false);
    });
    el.on("plotly_unhover", () => {
      if (state.suspendHover) return;
      setHighlight(null, id, false);
    });
    el.on("plotly_click", (ev) => {
      const pt = ev.points && ev.points[0];
      if (!pt) return;
      const satId = Array.isArray(pt.customdata) ? pt.customdata[0] : pt.customdata;
      // Click is the only gesture that scrolls the table to the row.
      if (typeof satId === "number") setHighlight(satId, id, true);
    });
  }
}

// ---------- Cross-highlight ------------------------------------------------

function findSatById(id) {
  return state.filtered.find((s) => s.id === id) || null;
}

function setHighlight(id, sourcePlotId, scroll = false) {
  // Short-circuit only when nothing would change: same id AND no new scroll
  // request. A click on an already-hovered point still needs to scroll.
  if (state.highlightId === id && !scroll) return;
  state.highlightId = id;
  state.suspendHover = true;

  const sat = id !== null ? findSatById(id) : null;

  // Plot 1: Perigee vs Apogee, overlay trace index 1
  Plotly.restyle(PLOTS.periApo, {
    x: [sat ? [sat.perigee_km] : []],
    y: [sat ? [sat.apogee_km] : []],
    customdata: [sat ? [sat.id] : []],
  }, [1]);

  // Plot 2: RAAN vs Inc, overlay trace index 1
  Plotly.restyle(PLOTS.raanInc, {
    x: [sat ? [sat.raan_deg] : []],
    y: [sat ? [sat.inclination_deg] : []],
    customdata: [sat ? [sat.id] : []],
  }, [1]);

  // Plot 3: 3D — overlay is the LAST trace
  const gd3d = document.getElementById(PLOTS.three);
  if (gd3d && gd3d.data && gd3d.data.length) {
    const lastIdx = gd3d.data.length - 1;
    Plotly.restyle(PLOTS.three, {
      x: [sat ? [sat.perigee_km] : []],
      y: [sat ? [sat.apogee_km] : []],
      z: [sat ? [sat.inclination_deg] : []],
      customdata: [sat ? [sat.id] : []],
    }, [lastIdx]);
  }

  highlightTableRow(id, scroll);

  // Clear suspend on next tick so user-initiated hovers resume
  setTimeout(() => { state.suspendHover = false; }, 30);
}

// ---------- Zone chips -----------------------------------------------------

function renderZoneChips() {
  const host = document.getElementById("zoneChipList");
  host.innerHTML = "";
  for (const zone of ZONE_ORDER) {
    const count = state.dataset.satellites.filter((s) => s.zone === zone).length;
    if (!count) continue;
    const chip = document.createElement("button");
    chip.className = "chip";
    chip.dataset.zone = zone;
    chip.dataset.active = "true";
    chip.innerHTML = `<span class="dot" style="background:${ZONE_COLORS[zone]}"></span>${zone} (${count})`;
    chip.addEventListener("click", () => {
      const active = chip.dataset.active === "true";
      chip.dataset.active = (!active).toString();
      if (active) state.enabledZones.delete(zone);
      else state.enabledZones.add(zone);
      applyFilters();
    });
    host.appendChild(chip);
  }
}

// ---------- Init -----------------------------------------------------------

function setupFilterInputs() {
  document.getElementById("searchInput").addEventListener("input", applyFilters);
  document.getElementById("includeExtended").addEventListener("change", applyFilters);
  document.querySelectorAll(".range-input").forEach((el) => {
    el.addEventListener("input", applyFilters);
  });
}

async function init() {
  setupSorting();
  setupFilterInputs();

  try {
    state.dataset = await loadDataset();
  } catch (err) {
    document.getElementById("stats").innerHTML = `
      <article class="stat">
        <div class="stat-label">Error loading orbits.json</div>
        <div class="stat-value" style="font-size:0.9rem">${String(err)}</div>
      </article>`;
    return;
  }

  renderZoneChips();
  applyFilters();
}

init();
