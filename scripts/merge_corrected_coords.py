#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
merge_corrected_coords.py
=========================
Merges coordinate corrections from three sources into monuments.json:
  1. OSM address matches   (matched_osm_addresses.json)   — HIGH priority
  2. pravo.by v2 coords    (pravo_heritage_protection_zones_v2.json) — HIGH/MEDIUM
  3. OSM memorial matches  (matched_osm_memorials.json)   — MEDIUM priority

Priority order (per monument, AT MOST ONE update applied):
  P1  OSM Address match, distance_discrepancy_m > 100
  P2  pravo v2, status=new_coordinates,       flagged_large_diameter=False, bbox<2500m
  P3  pravo v2, status=discrepancy_detected,  flagged_large_diameter=False, bbox<2500m, dist>500m
  P4  OSM Memorial, status=corrected_discrepancy, match_score >= 70
  P5  OSM Memorial, status=new_coordinates,       match_score >= 70

Never apply:
  - flagged_large_diameter=True in pravo
  - match_score < 65 in memorials
  - Coordinates outside Belarus (lat<51, lat>57, lon<23, lon>33)
"""
import json
import math
import sys
from pathlib import Path

import sys, io
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf-8-sig"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

# ── Belarus bounding box ──────────────────────────────────────────────────────
LAT_MIN, LAT_MAX = 51.0, 57.0
LON_MIN, LON_MAX = 23.0, 33.0


def in_belarus(lat, lon):
    return LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX


def haversine_m(lat1, lon1, lat2, lon2):
    """Great-circle distance in metres."""
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


# ── Loaders ───────────────────────────────────────────────────────────────────

def load_monuments():
    with open(DATA / "monuments.json", encoding="utf-8") as f:
        return json.load(f)


def load_osm_addresses():
    """Returns dict keyed by monument code."""
    with open(DATA / "matched_osm_addresses.json", encoding="utf-8") as f:
        d = json.load(f)
    return d.get("matches", {})


def load_osm_memorials():
    """Returns list of memorial match entries."""
    with open(DATA / "matched_osm_memorials.json", encoding="utf-8") as f:
        return json.load(f)


def load_pravo_v2():
    """Returns list of matched_monuments entries."""
    with open(DATA / "pravo_heritage_protection_zones_v2.json", encoding="utf-8") as f:
        d = json.load(f)
    return d.get("matched_monuments", [])


# ── Correction-map builder ────────────────────────────────────────────────────

def build_correction_map(monuments):
    """
    Build {code -> correction_entry} following strict priority rules.
    Returns the correction map and a dict of per-source statistics.
    """
    correction_map = {}          # code → correction entry
    rejected = []                # (code, reason)
    stats = {
        "p1_osm_address": 0,
        "p2_pravo_new": 0,
        "p3_pravo_discrepancy": 0,
        "p4_osm_memorial_corrected": 0,
        "p5_osm_memorial_new": 0,
        "rejected_outside_belarus": 0,
        "rejected_flagged_large": 0,
        "rejected_low_score": 0,
        "rejected_small_distance": 0,
    }

    # Build a quick lookup: code → monument (for old coords)
    monument_by_code = {}
    for m in monuments:
        monument_by_code[m["c"]] = m

    def try_register(code, lat, lon, source, confidence, distance_m, notes, priority_key):
        """Register correction if not already claimed at a higher priority and coords valid."""
        if code in correction_map:
            return False  # already claimed at higher priority
        if not in_belarus(lat, lon):
            stats["rejected_outside_belarus"] += 1
            rejected.append((code, f"outside Belarus ({lat:.4f},{lon:.4f})"))
            return False
        mon = monument_by_code.get(code)
        old_lat = mon.get("lat") if mon else None
        old_lon = mon.get("lon") if mon else None
        correction_map[code] = {
            "code": code,
            "lat": lat,
            "lon": lon,
            "old_lat": old_lat,
            "old_lon": old_lon,
            "source": source,
            "confidence": confidence,
            "distance_corrected_m": round(distance_m, 1) if distance_m is not None else None,
            "notes": notes,
            "priority": priority_key,
        }
        return True

    # ── P1: OSM Address matches ───────────────────────────────────────────────
    osm_addresses = load_osm_addresses()
    for code, match in osm_addresses.items():
        disc = match.get("distance_discrepancy_m", 0)
        if disc <= 100:
            stats["rejected_small_distance"] += 1
            continue
        lat = match["osm_coords"]["lat"]
        lon = match["osm_coords"]["lon"]
        if try_register(
            code, lat, lon,
            source="osm_address",
            confidence="high",
            distance_m=disc,
            notes=f"OSM building footprint ({match.get('osm_type_detail','')}) for {match.get('raw_address','')}, {disc:.0f}m from old coord",
            priority_key="P1",
        ):
            stats["p1_osm_address"] += 1

    # ── P2/P3: pravo.by v2 ───────────────────────────────────────────────────
    pravo_entries = load_pravo_v2()

    # Separate into new_coordinates and discrepancy_detected, sorted by priority
    pravo_new = [m for m in pravo_entries
                 if m.get("status") == "new_coordinates"
                 and not m.get("flagged_large_diameter")
                 and m.get("bbox_diameter_meters", 9999) < 2500]

    pravo_disc = [m for m in pravo_entries
                  if m.get("status") == "discrepancy_detected"
                  and not m.get("flagged_large_diameter")
                  and m.get("bbox_diameter_meters", 9999) < 2500]

    # Count rejected flagged_large entries
    for m in pravo_entries:
        if m.get("flagged_large_diameter") and m.get("status") in ("new_coordinates", "discrepancy_detected"):
            stats["rejected_flagged_large"] += 1

    # P2: pravo new_coordinates (previously coord-less monuments)
    for m in pravo_new:
        code = m["code"]
        lat, lon = m["pravo_lat"], m["pravo_lon"]
        bbox = m.get("bbox_diameter_meters", 0)
        if try_register(
            code, lat, lon,
            source="pravo_new",
            confidence="high",
            distance_m=None,
            notes=f"New coord from official decree (bbox={bbox:.0f}m)",
            priority_key="P2",
        ):
            stats["p2_pravo_new"] += 1

    # P3: pravo discrepancy_detected (dist must be > 500m per spec)
    for m in pravo_disc:
        code = m["code"]
        dist = m.get("distance_diff_meters", 0)
        if dist <= 500:
            stats["rejected_small_distance"] += 1
            continue
        lat, lon = m["pravo_lat"], m["pravo_lon"]
        bbox = m.get("bbox_diameter_meters", 0)
        if try_register(
            code, lat, lon,
            source="pravo_discrepancy",
            confidence="medium",
            distance_m=dist,
            notes=f"Discrepancy from official decree centroid, {dist:.0f}m from old coord (bbox={bbox:.0f}m)",
            priority_key="P3",
        ):
            stats["p3_pravo_discrepancy"] += 1

    # ── P4/P5: OSM memorial matches ──────────────────────────────────────────
    memorials = load_osm_memorials()

    mem_corrected = [m for m in memorials
                     if m.get("status") == "corrected_discrepancy"
                     and m.get("match_score", 0) >= 70]

    mem_new = [m for m in memorials
               if m.get("status") == "new_coordinates"
               and m.get("match_score", 0) >= 70]

    # Count low-score rejections
    for m in memorials:
        if m.get("status") in ("corrected_discrepancy", "new_coordinates"):
            if m.get("match_score", 0) < 65:
                stats["rejected_low_score"] += 1

    # P4: corrected discrepancy memorials
    for m in mem_corrected:
        code = m["code"]
        lat, lon = m["osm_lat"], m["osm_lon"]
        dist = m.get("distance_diff_meters", 0)
        score = m.get("match_score", 0)
        if try_register(
            code, lat, lon,
            source="osm_memorial_corrected",
            confidence="medium",
            distance_m=dist,
            notes=f"OSM memorial match (score={score}, dist={dist:.0f}m from old)",
            priority_key="P4",
        ):
            stats["p4_osm_memorial_corrected"] += 1

    # P5: new-coordinate memorials
    for m in mem_new:
        code = m["code"]
        lat, lon = m["osm_lat"], m["osm_lon"]
        score = m.get("match_score", 0)
        if try_register(
            code, lat, lon,
            source="osm_memorial_new",
            confidence="medium",
            distance_m=None,
            notes=f"OSM memorial new coord (score={score})",
            priority_key="P5",
        ):
            stats["p5_osm_memorial_new"] += 1

    return correction_map, stats, rejected


# ── Apply corrections to monuments ───────────────────────────────────────────

def apply_corrections(monuments, correction_map):
    """Return a new monuments list with corrected lat/lon applied."""
    updated = []
    applied_codes = set()
    for m in monuments:
        code = m["c"]
        if code in correction_map:
            entry = correction_map[code]
            m = dict(m)   # shallow copy
            m["lat"] = entry["lat"]
            m["lon"] = entry["lon"]
            applied_codes.add(code)
        updated.append(m)
    return updated, applied_codes


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("Loading monuments.json …")
    monuments = load_monuments()
    total = len(monuments)
    coords_before = sum(1 for m in monuments if m.get("lat") and m.get("lon"))

    print("Building correction map …")
    correction_map, stats, rejected = build_correction_map(monuments)

    print("Applying corrections …")
    monuments_corrected, applied_codes = apply_corrections(monuments, correction_map)
    coords_after = sum(1 for m in monuments_corrected if m.get("lat") and m.get("lon"))

    # ── Save correction map ───────────────────────────────────────────────────
    out_corrections = DATA / "coords_corrected.json"
    with open(out_corrections, "w", encoding="utf-8") as f:
        json.dump(list(correction_map.values()), f, ensure_ascii=False, indent=2)
    print(f"\nSaved {len(correction_map)} corrections → {out_corrections}")

    # ── Save corrected monuments ──────────────────────────────────────────────
    out_monuments = DATA / "monuments_corrected.json"
    with open(out_monuments, "w", encoding="utf-8") as f:
        json.dump(monuments_corrected, f, ensure_ascii=False, indent=2)
    print(f"Saved corrected monuments  → {out_monuments}")

    # ── Statistics ───────────────────────────────────────────────────────────
    total_updated = len(correction_map)
    print("\n" + "═" * 60)
    print("STATISTICS")
    print("═" * 60)
    print(f"Total monuments              : {total:,}")
    print(f"With coords BEFORE           : {coords_before:,}  ({coords_before/total*100:.1f}%)")
    print(f"With coords AFTER            : {coords_after:,}  ({coords_after/total*100:.1f}%)")
    print(f"Net coverage gain            : +{coords_after - coords_before:,}")
    print()
    print(f"Total corrections applied    : {total_updated:,}")
    print(f"  P1 OSM Address             : {stats['p1_osm_address']:,}")
    print(f"  P2 pravo.by new coords     : {stats['p2_pravo_new']:,}")
    print(f"  P3 pravo.by discrepancy    : {stats['p3_pravo_discrepancy']:,}")
    print(f"  P4 OSM memorial corrected  : {stats['p4_osm_memorial_corrected']:,}")
    print(f"  P5 OSM memorial new        : {stats['p5_osm_memorial_new']:,}")
    print()
    print(f"Rejected (outside Belarus)   : {stats['rejected_outside_belarus']:,}")
    print(f"Rejected (flagged large bbox): {stats['rejected_flagged_large']:,}")
    print(f"Rejected (low match score)   : {stats['rejected_low_score']:,}")
    print(f"Rejected (distance too small): {stats['rejected_small_distance']:,}")

    if rejected:
        print(f"\nRejected entries ({len(rejected)}):")
        for code, reason in rejected:
            print(f"  {code}: {reason}")

    print("═" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
