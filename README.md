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

## How orbital elements are extracted

### TLE line-2 column layout

A standard NORAD two-line element set is a fixed-width 80-column format.
Five quantities are sliced directly from line 2:

```
Column:  08-16   17-25   26-33           52-63
Field:   Inc(deg) RAAN(deg) Ecc(x10^-7) Mean motion(rev/day)
```

The epoch (the instant the elements are valid for) comes from line 1,
columns 18--32, encoded as a two-digit year plus fractional day-of-year.

Argument of perigee and mean anomaly are also present in line 2 but are
not used -- they describe where the satellite currently sits on its
ellipse, not the shape of the orbit itself.

### Raw value decoding

- **Inclination** and **RAAN** are stored in degrees and read directly.
- **Eccentricity** is stored as a 7-digit integer with an implicit
  leading `0.` (e.g. `9686250` means `0.9686250`).
- **Mean motion** is in revolutions per day and read directly.

### Derived quantities via Kepler's third law

Period, semi-major axis, perigee, and apogee are not stored in the TLE;
they are computed from eccentricity and mean motion:

```
period [day]  = 1 / mean_motion

n [rad/s]     = mean_motion * 2*pi / 86400

a [km]        = (mu / n^2) ^ (1/3)

perigee [km]  = a * (1 - e) - R_earth
apogee  [km]  = a * (1 + e) - R_earth
```

where:

- `mu = 398600.4418 km^3/s^2` (Earth's standard gravitational parameter)
- `R_earth = 6378.137 km` (mean equatorial radius)
- `n` is mean motion converted from rev/day to rad/s
  (`* 2*pi / 86400`)
- `a` is the semi-major axis from Kepler's third law: `n = sqrt(mu / a^3)`
  rearranged to `a = (mu / n^2)^(1/3)`
- Perigee and apogee altitudes are the nearest and farthest points of
  the ellipse (`a*(1-e)` and `a*(1+e)` for the center-relative radii)
  minus Earth's radius to convert to altitude above the surface.

### Extended-format TLEs (deep-space)

Some `.tle` files use Bill Gray's extended format, where the standard
element columns are replaced by six signed 8-digit hexadecimal numbers
encoding a position+velocity state vector. This happens when the orbit
is too extreme (hyperbolic, near-parabolic, or very high) for the
standard SDP4/SGP4 model to represent.

The parser detects this by checking whether the standard column slices
produce valid float tokens and a 7-digit eccentricity integer. If they
don't, the record is flagged `is_extended_format = True` and all element
fields are set to null. These objects are classified as `deep-space` and
appear in the catalog table but are excluded from the element-based
plots, because no orbital elements can be extracted without implementing
Bill Gray's custom state-vector propagator.

Example: NORAD 62719 (Falcon 9-427 Stage 2) has two entries in
`tle_list.txt`. The earlier file (`25010d.tle`, range 2025-01 to
2026-01) uses standard TLEs and parses normally. The newer file
(`25010d26v2.tle`, range 2026-01 to 2026-08) switched to extended
format because the trajectory became too extreme after re-fitting with
newer observations, so it shows no orbital elements in the web UI.

### TLE epoch parsing

The epoch field on line 1 (columns 18--32) encodes the time as:

```
YYDDD.DDDDDDDD
```

- `YY`: two-digit year (57--99 -> 1957--1999, 00--56 -> 2000--2056;
  the 1957 cutoff matches Sputnik, the first artificial satellite)
- `DDD.DDDDDDDD`: fractional day-of-year (1-indexed, so Jan 1 = day 1)

The parser converts this to a UTC datetime.

### Picking which TLE to use per satellite

Each `.tle` file typically contains many TLEs spanning weeks or months.
`build.py` picks one representative record per satellite:

1. If `tle_list.txt` specifies a `# Range: start end` for the entry,
   the TLE with epoch closest to the **midpoint** of that window is
   selected. The midpoint minimises the U-shaped error curve that
   results from TLE drift over time.
2. If only one endpoint is given, that date is used as the target.
3. If no range is specified, the most recent TLE is picked.

### What is not computed

- **SGP4 propagation** -- the catalog is a snapshot of elements at the
  picked epoch, not a real-time position predictor.
- **Perturbations** -- no J2, atmospheric drag, or luni-solar
  corrections are applied. The TLE's mean elements already incorporate
  these effects as modelled by SGP4/SDP4.
- **State-vector decoding** -- Bill Gray's extended hex format is not
  decoded; those entries are kept as deep-space placeholders.

## Source

TLE data: [Bill Gray / Project Pluto](https://www.projectpluto.com/tle_info.htm)
