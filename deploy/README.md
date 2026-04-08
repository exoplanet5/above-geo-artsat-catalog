---
title: Above-GEO Artsat Catalog
emoji: 🛰️
colorFrom: indigo
colorTo: yellow
sdk: static
app_file: index.html
pinned: false
short_description: xGEO, cislunar, translunar artsats from Bill Gray's TLE list
---

# Above-GEO Artificial Satellite Catalog

Interactive Plotly catalog of high-altitude artificial satellites parsed
from [Bill Gray's TLE list](https://github.com/Bill-Gray/tles). Only
objects with apogee above geostationary altitude (≥ 36 000 km) are
included; LEO/MEO and archived `old_tles/` entries are excluded.

## Plots

1. **Perigee vs Apogee** — log-log scatter, color = inclination.
2. **RAAN Ω vs Inclination** — color = log₁₀(period in days).
3. **3D orbit explorer** — Perigee × Apogee × Inclination, one trace per
   apogee zone (xGEO / cislunar / translunar / deep-space).
4. **Period histogram** — stacked log-period distribution per zone.

Hovering or clicking any point in plots 1–3 cross-highlights the same
satellite in the other plots and the catalog table.

## Apogee zones

| Zone        | Apogee range          |
| ----------- | --------------------- |
| xGEO        | 36 000 – 100 000 km   |
| cislunar    | 100 000 – 400 000 km  |
| translunar  | ≥ 400 000 km          |
| deep-space  | extended-format TLE   |

## Source

- Build script and full project: <https://github.com/YOUR_GITHUB_USER/YOUR_REPO>
- Underlying TLE list: <https://github.com/Bill-Gray/tles>
