#!/usr/bin/env python3
"""Build orbits.json catalog from Bill Gray TLE list.

Reads ~/tles/tle_list.txt, walks each `# Include` directive, parses the
referenced .tle file, computes classical orbital elements (RAAN,
inclination, period, perigee, apogee) for the representative epoch, and
writes a single JSON file consumed by the Plotly frontend.
"""
from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

UTC = timezone.utc
EARTH_MU = 398600.4418        # km^3/s^2
EARTH_RADIUS = 6378.137       # km
GEO_ALTITUDE_KM = 35786.0     # geostationary altitude
ABOVE_GEO_MIN_KM = 36000.0    # apogee threshold for "above GEO"
CISLUNAR_MIN_KM = 100_000.0   # xGEO -> cislunar boundary
TRANSLUNAR_MIN_KM = 400_000.0 # cislunar -> translunar boundary
SKIP_PATH_TOKENS = ("old_tles/", "old_tles\\")


# ---------- TLE parsing ----------------------------------------------------

@dataclass
class TleRecord:
    name: str | None
    line1: str
    line2: str
    epoch_utc: datetime | None
    inclination_deg: float | None
    raan_deg: float | None
    eccentricity: float | None
    mean_motion_rev_day: float | None
    period_day: float | None
    perigee_km: float | None
    apogee_km: float | None
    is_extended_format: bool


def _is_float_token(s: str) -> bool:
    return bool(re.fullmatch(r"[+-]?\d+(?:\.\d+)?", s))


def parse_flexible_date(token: str | None) -> datetime | None:
    if not token:
        return None
    token = token.strip()
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})(\.\d+)?", token)
    if m:
        y, mo, d = map(int, m.group(1, 2, 3))
        frac = float(m.group(4)) if m.group(4) else 0.0
        return datetime(y, mo, d, tzinfo=UTC) + timedelta(days=frac)
    m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})(\.\d+)?", token)
    if m:
        y, mo, d = map(int, m.group(1, 2, 3))
        frac = float(m.group(4)) if m.group(4) else 0.0
        return datetime(y, mo, d, tzinfo=UTC) + timedelta(days=frac)
    return None


def parse_tle_epoch(line1: str) -> datetime | None:
    if len(line1) < 32:
        return None
    field = line1[18:32].strip()
    if len(field) < 5:
        return None
    try:
        yy = int(field[:2])
        doy = float(field[2:])
    except ValueError:
        return None
    year = 1900 + yy if yy >= 57 else 2000 + yy
    return datetime(year, 1, 1, tzinfo=UTC) + timedelta(days=doy - 1.0)


def compute_orbit_metrics(line2: str) -> dict | None:
    if len(line2) < 63:
        return None
    inc_t = line2[8:16].strip()
    raan_t = line2[17:25].strip()
    ecc_t = line2[26:33].strip()
    mm_t = line2[52:63].strip()
    if not (_is_float_token(inc_t) and _is_float_token(raan_t) and _is_float_token(mm_t)):
        return None
    if not re.fullmatch(r"\d{1,7}", ecc_t):
        return None

    inc = float(inc_t)
    raan = float(raan_t)
    ecc = float(f"0.{ecc_t}")
    mm_rev_day = float(mm_t)
    if mm_rev_day <= 0:
        return None

    period_day = 1.0 / mm_rev_day
    n_rad_s = mm_rev_day * 2.0 * math.pi / 86400.0
    a_km = (EARTH_MU / (n_rad_s ** 2)) ** (1.0 / 3.0)
    perigee = a_km * (1.0 - ecc) - EARTH_RADIUS
    apogee = a_km * (1.0 + ecc) - EARTH_RADIUS
    return {
        "inclination_deg": inc,
        "raan_deg": raan,
        "eccentricity": ecc,
        "mean_motion_rev_day": mm_rev_day,
        "period_day": period_day,
        "semi_major_axis_km": a_km,
        "perigee_km": perigee,
        "apogee_km": apogee,
    }


def parse_tle_file(path: Path) -> list[TleRecord]:
    out: list[TleRecord] = []
    if not path.exists():
        return out
    name: str | None = None
    line1: str | None = None
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            line = raw.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            if line.startswith("1 "):
                line1 = line
                continue
            if line.startswith("2 ") and line1:
                m = compute_orbit_metrics(line)
                ep = parse_tle_epoch(line1)
                out.append(TleRecord(
                    name=name,
                    line1=line1,
                    line2=line,
                    epoch_utc=ep,
                    inclination_deg=m["inclination_deg"] if m else None,
                    raan_deg=m["raan_deg"] if m else None,
                    eccentricity=m["eccentricity"] if m else None,
                    mean_motion_rev_day=m["mean_motion_rev_day"] if m else None,
                    period_day=m["period_day"] if m else None,
                    perigee_km=m["perigee_km"] if m else None,
                    apogee_km=m["apogee_km"] if m else None,
                    is_extended_format=m is None,
                ))
                line1 = None
                continue
            name = line.strip() or None
    return out


# ---------- tle_list.txt parsing -------------------------------------------

@dataclass
class ListEntry:
    include_file: str
    range_start: datetime | None
    range_end: datetime | None
    norad_id: int | None
    cospar_id: str | None
    max_error_deg: float | None


def parse_tle_list(path: Path) -> list[ListEntry]:
    entries: list[ListEntry] = []
    range_start = range_end = None
    norad: int | None = None
    cospar: str | None = None
    max_err: float | None = None
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            line = raw.strip()
            if not line:
                continue
            if line.startswith("# Max error"):
                m = re.search(r"Max error\s+([0-9.]+)", line)
                if m:
                    max_err = float(m.group(1))
                continue
            if line.startswith("# Range:"):
                payload = line.split(":", 1)[1].strip().split()
                range_start = parse_flexible_date(payload[0]) if payload else None
                range_end = parse_flexible_date(payload[1]) if len(payload) > 1 else None
                continue
            if line.startswith("# ID:"):
                payload = line.split(":", 1)[1].strip().split()
                norad = int(payload[0]) if payload and payload[0].isdigit() else None
                cospar = payload[1] if len(payload) > 1 else None
                continue
            if line.startswith("# Include"):
                inc = line.split(None, 2)[2].strip()
                entries.append(ListEntry(inc, range_start, range_end, norad, cospar, max_err))
    return entries


def pick_record(records: Iterable[TleRecord],
                rs: datetime | None,
                re_: datetime | None) -> TleRecord | None:
    recs = list(records)
    if not recs:
        return None
    with_epoch = [r for r in recs if r.epoch_utc is not None]
    if not with_epoch:
        return recs[-1]
    if rs and re_:
        target = rs + (re_ - rs) / 2
    elif re_:
        target = re_
    elif rs:
        target = rs
    else:
        return max(with_epoch, key=lambda r: r.epoch_utc)
    return min(with_epoch, key=lambda r: abs((r.epoch_utc - target).total_seconds()))


# ---------- Orbit zone classification --------------------------------------
# Three apogee bands above GEO:
#   xGEO       :    36 000 <= apogee <  100 000 km
#   cislunar   :   100 000 <= apogee <  400 000 km
#   translunar :   400 000 <= apogee  (lunar distance and beyond)
# Extended-format TLEs are deep-space by construction in Bill Gray's list,
# so they get the "deep-space" label without trying to read elements.

def classify_zone(apogee_km: float | None, is_extended: bool) -> str:
    if is_extended:
        return "deep-space"
    if apogee_km is None:
        return "unknown"
    if apogee_km < CISLUNAR_MIN_KM:
        return "xGEO"
    if apogee_km < TRANSLUNAR_MIN_KM:
        return "cislunar"
    return "translunar"


# ---------- Dataset assembly -----------------------------------------------

def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat().replace("+00:00", "Z") if dt else None


def _round(v: float | None, n: int = 6) -> float | None:
    return round(v, n) if v is not None else None


def _is_skipped(include_file: str) -> bool:
    return any(tok in include_file for tok in SKIP_PATH_TOKENS)


def build_dataset(tle_root: Path, tle_list: Path) -> dict:
    entries = parse_tle_list(tle_list)

    skipped_old = 0
    skipped_below_geo = 0
    skipped_no_data = 0
    sats: list[dict] = []
    next_id = 1

    for e in entries:
        if _is_skipped(e.include_file):
            skipped_old += 1
            continue

        recs = parse_tle_file(tle_root / e.include_file)
        best = pick_record(recs, e.range_start, e.range_end)

        if best is None:
            skipped_no_data += 1
            continue

        # Drop classical entries that are not above GEO. Extended-format TLEs
        # are deep-space by construction in Bill Gray's list, so we keep them
        # even though their elements are not parseable.
        if best.is_extended_format is False:
            if best.apogee_km is None or best.apogee_km < ABOVE_GEO_MIN_KM:
                skipped_below_geo += 1
                continue

        period_day = _round(best.period_day, 8)
        peri = _round(best.perigee_km, 3)
        apo = _round(best.apogee_km, 3)
        inc = _round(best.inclination_deg, 4)
        zone = classify_zone(apo, best.is_extended_format)

        sats.append({
            "id": next_id,
            "include_file": e.include_file,
            "norad_id": e.norad_id,
            "cospar_id": e.cospar_id,
            "range_start_utc": _iso(e.range_start),
            "range_end_utc": _iso(e.range_end),
            "max_error_deg": e.max_error_deg,
            "name": best.name,
            "tle_epoch_utc": _iso(best.epoch_utc),
            "is_extended_format": best.is_extended_format,
            "raan_deg": _round(best.raan_deg, 4),
            "inclination_deg": inc,
            "eccentricity": _round(best.eccentricity, 8),
            "period_day": period_day,
            "perigee_km": peri,
            "apogee_km": apo,
            "zone": zone,
        })
        next_id += 1

    classical = sum(1 for s in sats if s["is_extended_format"] is False)
    extended = sum(1 for s in sats if s["is_extended_format"] is True)

    return {
        "meta": {
            "generated_at_utc": _iso(datetime.now(tz=UTC)),
            "tle_root": str(tle_root),
            "tle_list_path": str(tle_list),
            "above_geo_threshold_km": ABOVE_GEO_MIN_KM,
            "cislunar_threshold_km": CISLUNAR_MIN_KM,
            "translunar_threshold_km": TRANSLUNAR_MIN_KM,
            "total_entries": len(sats),
            "classical_entries": classical,
            "extended_entries": extended,
            "skipped_old_tles": skipped_old,
            "skipped_below_geo": skipped_below_geo,
            "skipped_no_data": skipped_no_data,
        },
        "satellites": sats,
    }


def main() -> int:
    project = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="Build orbits.json from a Bill Gray TLE list")
    parser.add_argument("--tle-root", type=Path, default=Path("/Users/mickey/tles"))
    parser.add_argument("--tle-list", type=Path, default=Path("/Users/mickey/tles/tle_list.txt"))
    parser.add_argument("--out", type=Path, default=project / "data" / "orbits.json")
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    dataset = build_dataset(args.tle_root.expanduser().resolve(),
                            args.tle_list.expanduser().resolve())
    args.out.write_text(json.dumps(dataset, indent=2), encoding="utf-8")

    meta = dataset["meta"]
    print(f"wrote {args.out}")
    print(f"  kept (above GEO)  : {meta['total_entries']}")
    print(f"    classical       : {meta['classical_entries']}")
    print(f"    extended        : {meta['extended_entries']}")
    print(f"  skipped old_tles  : {meta['skipped_old_tles']}")
    print(f"  skipped below GEO : {meta['skipped_below_geo']}")
    print(f"  skipped no data   : {meta['skipped_no_data']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
