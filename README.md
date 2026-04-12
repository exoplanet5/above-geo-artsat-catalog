# High Orbit Artsat Catalog

Interactive statistics tool for high-altitude artificial satellites, built on
[Bill Gray's TLE list](https://www.projectpluto.com/tle_info.htm). Only objects
with apogee above geostationary altitude (>= 36 000 km) are included; LEO/MEO
and archived `old_tles/` entries are excluded.

Live demo: <https://zhuoxiaowang-above-geo-artsat-catalog.static.hf.space>

## Orbit regime zones

Classification is based on apogee altitude:

| Zone | Apogee range | Description |
|---|---|---|
| **xGEO** | 36 000 -- 100 000 km | Supersynchronous, graveyard, GTO-like |
| **cislunar** | 100 000 -- 400 000 km | Earth--Moon neighborhood |
| **translunar** | >= 400 000 km | Lunar distance and beyond |
| **deep-space** | extended-format TLE | Too far for standard 80-column TLEs |

Extended-format TLEs use Bill Gray's wider column layout for objects whose
orbits cannot be represented in the NORAD 80-column format. Their orbital
elements are not parsed, so they appear in the table but not in the
element-based plots.

## Plots

1. **Perigee vs Apogee** -- log-log scatter, color-coded by inclination.
2. **RAAN Omega vs Inclination** -- color-coded by log10(period in days).
3. **3D orbit explorer** -- Perigee x Apogee x Inclination, one trace per
   zone with legend toggle.
4. **Period histogram** -- stacked log-period distribution by zone.

Hovering any point cross-highlights the same satellite across all plots.
Clicking a point scrolls the catalog table to the matching row.

## Project layout

```
catalog/
  build.py            # Parse ~/tles/tle_list.txt -> data/orbits.json
  serve.py            # Local dev server (port 8090)
  Makefile            # build, serve, dist, release targets
  data/
    orbits.json       # Generated catalog (committed for CI)
  web/
    index.html        # Single-page app
    app.js            # Plotly frontend + cross-highlight logic
    styles.css        # Dark theme
  deploy/
    README.md         # HF Spaces YAML frontmatter
  .github/workflows/
    sync-hf.yml       # Auto-sync dist/ to HF Space on push
  DEPLOY.md           # Full deployment instructions
```

## Quick start

### Prerequisites

- Python 3.10+
- Bill Gray's TLE files at `~/tles/` (with `tle_list.txt` manifest)

### Build and preview locally

```bash
# Parse TLEs and generate data/orbits.json
make build

# Start the dev server and open in browser
make run
# -> http://127.0.0.1:8090
```

### Deploy to Hugging Face Spaces

The GitHub Action (`.github/workflows/sync-hf.yml`) auto-syncs to an HF
Static Space on every push to `main`. See [DEPLOY.md](DEPLOY.md) for
setup steps (HF token, repo variable, first trigger).

## Data pipeline

1. `build.py` reads `~/tles/tle_list.txt`, walks each `# Include` directive,
   and parses the referenced `.tle` files.
2. For each satellite it extracts inclination, RAAN, eccentricity, and mean
   motion from the standard TLE line-2 columns, then derives period,
   semi-major axis, perigee, and apogee via Kepler's third law.
3. Satellites with apogee below 36 000 km and entries from `old_tles/` are
   filtered out.
4. Each satellite is classified into an apogee zone and written to
   `data/orbits.json`.

## Source

TLE data: [Bill Gray / Project Pluto](https://www.projectpluto.com/tle_info.htm)
