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
AU_KM = 149_597_870.7         # 1 AU in km
GEO_ALTITUDE_KM = 35786.0     # geostationary altitude
ABOVE_GEO_MIN_KM = 36000.0    # apogee threshold for "above GEO"
CISLUNAR_MIN_KM = 100_000.0   # xGEO -> cislunar boundary
TRANSLUNAR_MIN_KM = 400_000.0 # cislunar -> translunar boundary
SKIP_PATH_TOKENS = ("old_tles/", "old_tles\\")
# If `a` (semi-major axis) in the comment block is below this threshold
# it is in AU (heliocentric orbit); above it, in km (geocentric orbit).
_A_AU_KM_THRESHOLD = 1000.0


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


# ---------- Extended-format comment element extraction ---------------------
# Bill Gray's extended-format TLE files often contain the fitted orbital
# elements in comment lines at the top of the file, e.g.:
#
#   # n  14.48632678                       Peri.  349.55576
#   # a 359720.059                         Node    35.97001
#   # e   0.3587265                        Incl.   41.37743
#   # P  24.8510d                H 26.57  G  0.15   U  6.1
#
# For geocentric orbits `a` is in km; for heliocentric ones it is in AU.
# We extract what we can and derive perigee/apogee for the geocentric case.

_RE_A_NODE = re.compile(
    r"^#\s+a\s+([\d.]+)"          # semi-major axis
    r".*?Node\s+([\d.]+)",         # RAAN (Node)
)
_RE_E_INCL = re.compile(
    r"^#\s+e\s+([\d.]+)"          # eccentricity
    r".*?Incl\.\s+([\d.]+)",       # inclination
)
_RE_PERIOD = re.compile(
    r"^#\s+P\s+(?:[\d.]+/)?"      # optional years prefix "1.01/"
    r"([\d.]+)d",                  # period in days
)


def parse_comment_elements(path: Path) -> dict | None:
    """Extract orbital elements from comment header of an extended-format
    TLE file.  Returns a dict with keys matching compute_orbit_metrics()
    output, or None if the comment block lacks the expected lines."""
    a_val = node_val = e_val = incl_val = period_val = None

    if not path.exists():
        return None
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            line = raw.rstrip("\n")
            if not line.startswith("#"):
                # Stop scanning once we leave the comment header, but only
                # if we haven't found anything yet — some files interleave
                # comment blocks between TLE groups.
                if a_val is not None:
                    break
                continue

            m = _RE_A_NODE.match(line)
            if m:
                a_val = float(m.group(1))
                node_val = float(m.group(2))
                continue
            m = _RE_E_INCL.match(line)
            if m:
                e_val = float(m.group(1))
                incl_val = float(m.group(2))
                continue
            m = _RE_PERIOD.search(line)
            if m:
                period_val = float(m.group(1))
                continue

    if a_val is None or e_val is None:
        return None

    # Determine geocentric (a in km) vs heliocentric (a in AU).
    if a_val < _A_AU_KM_THRESHOLD:
        # Heliocentric — perigee/apogee from Earth are meaningless.
        return {
            "inclination_deg": incl_val,
            "raan_deg": node_val,
            "eccentricity": e_val,
            "mean_motion_rev_day": (1.0 / period_val) if period_val else None,
            "period_day": period_val,
            "semi_major_axis_km": None,
            "perigee_km": None,
            "apogee_km": None,
            "heliocentric": True,
        }

    # Geocentric — compute perigee/apogee altitudes.
    perigee = a_val * (1.0 - e_val) - EARTH_RADIUS
    apogee = a_val * (1.0 + e_val) - EARTH_RADIUS
    mm = (1.0 / period_val) if period_val else None

    return {
        "inclination_deg": incl_val,
        "raan_deg": node_val,
        "eccentricity": e_val,
        "mean_motion_rev_day": mm,
        "period_day": period_val,
        "semi_major_axis_km": a_val,
        "perigee_km": perigee,
        "apogee_km": apogee,
        "heliocentric": False,
    }


# ---------- Extended-format state-vector extraction via get_vect -----------
# Bill Gray's `get_vect` decodes a hex-format TLE into a J2000 equatorial
# geocentric state vector (position in km, velocity in km/s) at a given
# instant.  We convert that state vector to classical (osculating)
# Keplerian elements.  This is the fallback for extended-format TLE
# files that lack the comment-header element block.

import subprocess
import shutil

GET_VECT_BIN = Path("/Users/mickey/Desktop/billgray/sat_code/get_vect")
# Rough TAI-UTC + 32.184s leap offset for 2020-2030.  Good enough to pick
# a point inside the TLE's validity window; we only want stable elements,
# not a precise ephemeris position.
DELTA_T_SEC = 69.2
J2000_JD = 2451545.0  # 2000-01-01 12:00 UTC


def _jd_tdt_from_utc(dt: datetime) -> float:
    """Convert a UTC datetime to approximate JD TDT."""
    utc = dt.astimezone(UTC)
    days_since_j2000 = (utc - datetime(2000, 1, 1, 12, 0, tzinfo=UTC)).total_seconds() / 86400.0
    return J2000_JD + days_since_j2000 + DELTA_T_SEC / 86400.0


def _parse_get_vect_output(text: str) -> tuple[list[float], list[float]] | None:
    """Parse `get_vect` stdout. Returns (r_km[3], v_km_s[3]) for the first
    state vector emitted, or None if no vector is present."""
    # Data lines look like:
    #  -467538.13198 -177348.94474 110920.45433 0408   # Ctr 3 km sec eq
    #   0.02816 -0.56614 -0.43637 0 0 0
    # We want two consecutive lines: first has ~3 large floats (position
    # km), second has ~3 small floats (velocity km/s).
    lines = [ln.rstrip() for ln in text.splitlines()]
    for i in range(len(lines) - 1):
        parts1 = lines[i].split()
        parts2 = lines[i + 1].split()
        if len(parts1) < 3 or len(parts2) < 3:
            continue
        try:
            rx, ry, rz = float(parts1[0]), float(parts1[1]), float(parts1[2])
            vx, vy, vz = float(parts2[0]), float(parts2[1]), float(parts2[2])
        except ValueError:
            continue
        # Position magnitude > 6000 km (above Earth's surface) and velocity
        # magnitude < 50 km/s (escape speed at Earth's surface ~ 11.2 km/s,
        # plenty of headroom for escape trajectories).
        r_mag = math.sqrt(rx * rx + ry * ry + rz * rz)
        v_mag = math.sqrt(vx * vx + vy * vy + vz * vz)
        if r_mag < 6000 or v_mag > 50:
            continue
        return ([rx, ry, rz], [vx, vy, vz])
    return None


def get_state_vector(tle_path: Path, norad_id: int, jd_tdt: float) -> tuple[list[float], list[float]] | None:
    """Run `get_vect` against a TLE file at a given JD TDT. Returns
    (r_km[3], v_km_s[3]) in J2000 geocentric, or None on failure."""
    if not GET_VECT_BIN.exists() or shutil.which(str(GET_VECT_BIN)) is None:
        return None
    try:
        proc = subprocess.run(
            [str(GET_VECT_BIN), str(tle_path), "-n", str(norad_id), "-t", f"{jd_tdt:.6f}"],
            capture_output=True, text=True, timeout=8, cwd="/tmp",
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    return _parse_get_vect_output(proc.stdout)


def osculating_elements(r_vec: list[float], v_vec: list[float]) -> dict | None:
    """Convert a geocentric state vector (J2000, km, km/s) to classical
    Keplerian elements. Returns None if the geometry is degenerate."""
    rx, ry, rz = r_vec
    vx, vy, vz = v_vec
    r = math.sqrt(rx * rx + ry * ry + rz * rz)
    v2 = vx * vx + vy * vy + vz * vz
    if r < 1e-6:
        return None

    # Specific orbital energy. energy < 0 => bound ellipse.
    energy = 0.5 * v2 - EARTH_MU / r
    if abs(energy) < 1e-12:
        return None  # parabolic, skip
    a_km = -EARTH_MU / (2.0 * energy)

    # Specific angular momentum h = r x v.
    hx = ry * vz - rz * vy
    hy = rz * vx - rx * vz
    hz = rx * vy - ry * vx
    h_mag = math.sqrt(hx * hx + hy * hy + hz * hz)
    if h_mag < 1e-6:
        return None  # radial trajectory, undefined plane

    # Eccentricity vector e_vec = (v x h)/mu - r_hat.
    evx = (vy * hz - vz * hy) / EARTH_MU - rx / r
    evy = (vz * hx - vx * hz) / EARTH_MU - ry / r
    evz = (vx * hy - vy * hx) / EARTH_MU - rz / r
    ecc = math.sqrt(evx * evx + evy * evy + evz * evz)

    # Inclination.
    cos_inc = max(-1.0, min(1.0, hz / h_mag))
    inc_deg = math.degrees(math.acos(cos_inc))

    # RAAN (node vector = z_hat x h, so nx = -hy, ny = hx, nz = 0).
    nx, ny = -hy, hx
    n_mag = math.sqrt(nx * nx + ny * ny)
    if n_mag < 1e-9:
        raan_deg = 0.0
    else:
        cos_raan = max(-1.0, min(1.0, nx / n_mag))
        raan_deg = math.degrees(math.acos(cos_raan))
        if ny < 0:
            raan_deg = 360.0 - raan_deg

    result: dict = {
        "inclination_deg": inc_deg,
        "raan_deg": raan_deg,
        "eccentricity": ecc,
        "semi_major_axis_km": a_km if energy < 0 else None,
        "perigee_km": None,
        "apogee_km": None,
        "period_day": None,
        "mean_motion_rev_day": None,
        "bound": energy < 0 and ecc < 1.0,
    }

    if result["bound"]:
        # Bound ellipse: period from Kepler's third law, perigee/apogee as
        # altitudes above Earth's mean radius.
        period_s = 2.0 * math.pi * math.sqrt((a_km ** 3) / EARTH_MU)
        result["period_day"] = period_s / 86400.0
        result["mean_motion_rev_day"] = 86400.0 / period_s
        result["perigee_km"] = a_km * (1.0 - ecc) - EARTH_RADIUS
        result["apogee_km"] = a_km * (1.0 + ecc) - EARTH_RADIUS
    return result


def extract_state_vector_elements(tle_path: Path, norad_id: int | None,
                                   epoch_utc: datetime | None) -> dict | None:
    """Run get_vect on `tle_path` at `epoch_utc` (UTC), convert the state
    vector to osculating Keplerian elements. Returns a dict in the same
    shape as parse_comment_elements, or None on failure."""
    if norad_id is None or epoch_utc is None:
        return None
    jd_tdt = _jd_tdt_from_utc(epoch_utc)
    sv = get_state_vector(tle_path, norad_id, jd_tdt)
    if sv is None:
        return None
    r_vec, v_vec = sv
    elems = osculating_elements(r_vec, v_vec)
    if elems is None:
        return None
    return {
        "inclination_deg": elems["inclination_deg"],
        "raan_deg": elems["raan_deg"],
        "eccentricity": elems["eccentricity"],
        "mean_motion_rev_day": elems["mean_motion_rev_day"],
        "period_day": elems["period_day"],
        "semi_major_axis_km": elems["semi_major_axis_km"],
        "perigee_km": elems["perigee_km"],
        "apogee_km": elems["apogee_km"],
        "heliocentric": not elems["bound"],
    }


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
# Extended-format TLEs without a parseable apogee (heliocentric, or no
# comment elements) remain "deep-space".  Those where we extracted
# geocentric elements from the comment header are classified by apogee.

def classify_zone(apogee_km: float | None, is_extended: bool) -> str:
    if apogee_km is None:
        return "deep-space" if is_extended else "unknown"
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
    extended_backfilled = 0
    sats: list[dict] = []
    next_id = 1
    # Cache comment-element lookups per file (many entries may share one).
    _comment_cache: dict[str, dict | None] = {}

    for e in entries:
        if _is_skipped(e.include_file):
            skipped_old += 1
            continue

        tle_path = tle_root / e.include_file
        recs = parse_tle_file(tle_path)
        best = pick_record(recs, e.range_start, e.range_end)

        if best is None:
            skipped_no_data += 1
            continue

        # For extended-format records, try to backfill orbital elements.
        # Two stages in order of preference:
        #   1. Comment-header block (mean elements from find_orb's fit).
        #   2. Fall back to get_vect + osculating elements from the hex
        #      state vector at the picked TLE epoch.
        if best.is_extended_format:
            if e.include_file not in _comment_cache:
                _comment_cache[e.include_file] = parse_comment_elements(tle_path)
            ce = _comment_cache[e.include_file]
            if ce is None:
                ce = extract_state_vector_elements(tle_path, e.norad_id, best.epoch_utc)
            if ce is not None:
                best.inclination_deg = ce["inclination_deg"]
                best.raan_deg = ce["raan_deg"]
                best.eccentricity = ce["eccentricity"]
                best.mean_motion_rev_day = ce["mean_motion_rev_day"]
                best.period_day = ce["period_day"]
                best.perigee_km = ce["perigee_km"]
                best.apogee_km = ce["apogee_km"]
                extended_backfilled += 1

        # Drop classical entries that are not above GEO. Extended-format TLEs
        # with geocentric apogee are also filtered by the same threshold.
        # Extended-format TLEs without parseable apogee (heliocentric, or
        # no comment elements) are always kept.
        if best.is_extended_format is False:
            if best.apogee_km is None or best.apogee_km < ABOVE_GEO_MIN_KM:
                skipped_below_geo += 1
                continue
        elif best.apogee_km is not None and best.apogee_km < ABOVE_GEO_MIN_KM:
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
            "extended_backfilled": extended_backfilled,
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
    print(f"    ext. backfilled : {meta['extended_backfilled']}")
    print(f"  skipped old_tles  : {meta['skipped_old_tles']}")
    print(f"  skipped below GEO : {meta['skipped_below_geo']}")
    print(f"  skipped no data   : {meta['skipped_no_data']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
