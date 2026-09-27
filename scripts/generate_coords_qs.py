#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_coords_qs.py
=====================
Generates Wikidata QuickStatements for coordinate corrections.

For each corrected monument in data/coords_corrected.json:
  1. Look up QID via bulk SPARQL cache (P632) — built/refreshed automatically
  2. Fall back to per-code wbsearchentities API for uncached codes
  3. Generate QuickStatement:  QID<TAB>P625<TAB>@LAT/LON
  4. Save to data/qs_coord_corrections.qs
  5. Save summary CSV to data/coord_corrections_summary.csv

QID strategy (fastest-first):
  a) local file wikidata_p632_cache.json (built by a bulk SPARQL call)
  b) exhibits_indexed.json 'qid' field (if present in future)
  c) Wikidata wbsearchentities API -- only for uncached codes, rate-limited
"""
import csv
import io
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

# Force UTF-8 output on Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf-8-sig"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

EXHIBITS_INDEX = ROOT.parent / "heritage-wrapper" / "data" / "exhibits_indexed.json"
WIKIDATA_API   = "https://www.wikidata.org/w/api.php"
WDQS_ENDPOINT  = "https://query.wikidata.org/sparql"
P632_CACHE     = DATA / "wikidata_p632_cache.json"

USER_AGENT = "wlm-belarus-coord-sync/1.0 (https://github.com/uladzcz/wlm-belarus)"

# Rate-limiting: minimum seconds between individual Wikidata API calls
API_DELAY = 1.2


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_corrections():
    path = DATA / "coords_corrected.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_monuments():
    with open(DATA / "monuments.json", encoding="utf-8") as f:
        return json.load(f)


def build_monument_index(monuments):
    """Returns dict: code -> monument entry (for title lookup)."""
    return {m["c"]: m for m in monuments}


def load_sparql_cache():
    """
    Load the pre-built P632 SPARQL cache {code -> QID}.
    Returns empty dict if file not present.
    """
    if not P632_CACHE.exists():
        return {}
    with open(P632_CACHE, encoding="utf-8") as f:
        cache = json.load(f)
    print(f"  Loaded {len(cache):,} QIDs from wikidata_p632_cache.json")
    return cache


def build_sparql_cache():
    """
    Execute a bulk SPARQL query to fetch ALL P632 (Belarus heritage code) items.
    Saves result to P632_CACHE.  Returns the cache dict.
    """
    sparql = "SELECT ?item ?code WHERE { ?item wdt:P632 ?code . }"
    req = urllib.request.Request(
        WDQS_ENDPOINT + "?" + urllib.parse.urlencode({"query": sparql, "format": "json"}),
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    print("  Querying Wikidata SPARQL for all P632 entries …")
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read().decode("utf-8"))
    bindings = data.get("results", {}).get("bindings", [])
    cache = {}
    for b in bindings:
        qid  = b["item"]["value"].split("/")[-1]
        code = b["code"]["value"]
        # Keep first QID seen per code (shouldn't normally collide)
        cache.setdefault(code, qid)
    with open(P632_CACHE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    print(f"  Saved {len(cache):,} entries to wikidata_p632_cache.json")
    return cache


def load_exhibits_qid_cache():
    """
    Load exhibits_indexed.json and return {code -> QID} for any entries
    that already have a 'qid' / 'wikidata' field.
    """
    if not EXHIBITS_INDEX.exists():
        return {}
    with open(EXHIBITS_INDEX, encoding="utf-8") as f:
        exhibits = json.load(f)
    cache = {}
    for e in exhibits:
        qid = e.get("qid") or e.get("wikidata") or e.get("wd")
        if qid:
            cache[e["code"]] = qid
    if cache:
        print(f"  Loaded {len(cache):,} QIDs from exhibits_indexed.json")
    return cache


def query_wikidata_for_qid(code: str) -> str | None:
    """
    Fallback: search Wikidata by text for the heritage code.
    Returns QID string ('Q12345') or None.
    Note: Results are approximate — text search is not exact.
    """
    params = {
        "action":   "wbsearchentities",
        "search":   code,
        "language": "be",
        "format":   "json",
        "limit":    "5",
        "type":     "item",
    }
    req = urllib.request.Request(
        WIKIDATA_API + "?" + urllib.parse.urlencode(params),
        headers={"User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        time.sleep(API_DELAY)
        results = data.get("search", [])
        # Only return the first proper Q-item
        for r in results:
            qid = r.get("id", "")
            if qid.startswith("Q"):
                return qid
    except Exception as exc:
        print(f"  [WARN] Wikidata API error for {code}: {exc}", file=sys.stderr)
        time.sleep(API_DELAY)
    return None


def format_qs_coord(lat: float, lon: float) -> str:
    """Format coordinate for QuickStatements: @LAT/LON (6 decimal places)."""
    return f"@{lat:.6f}/{lon:.6f}"


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("Loading corrections …")
    corrections = load_corrections()
    print(f"  {len(corrections):,} corrections to process")

    print("Loading monuments for title lookup …")
    monuments  = load_monuments()
    mon_index  = build_monument_index(monuments)

    # ── Build QID lookup from multiple sources ────────────────────────────────
    print("\nBuilding QID cache …")

    # Source A: SPARQL bulk cache (P632)
    qid_cache = load_sparql_cache()
    if not qid_cache:
        try:
            qid_cache = build_sparql_cache()
        except Exception as exc:
            print(f"  [WARN] SPARQL bulk fetch failed: {exc}; will fall back to per-code API")

    # Source B: exhibits_indexed.json (future-proofing)
    exhibits_cache = load_exhibits_qid_cache()
    qid_cache.update({k: v for k, v in exhibits_cache.items() if k not in qid_cache})

    qs_lines       = []
    csv_rows       = []
    api_queries    = 0
    qids_found     = 0
    qids_not_found = 0

    print("\nProcessing corrections …")
    for corr in corrections:
        code    = corr["code"]
        lat     = corr["lat"]
        lon     = corr["lon"]
        old_lat = corr.get("old_lat")
        old_lon = corr.get("old_lon")
        source  = corr["source"]
        dist_m  = corr.get("distance_corrected_m")
        notes   = corr.get("notes", "")

        mon   = mon_index.get(code, {})
        title = mon.get("t", "")

        # Heritage codes with sub-item suffix (e.g. 123Ж000079_7) —
        # Wikidata P632 typically stores only the root code without suffix.
        root_code = code.split("_")[0] if "_" in code else code

        qid = qid_cache.get(code) or qid_cache.get(root_code)

        if not qid:
            # Fallback: per-code API query (rate-limited)
            api_queries += 1
            if api_queries % 20 == 0:
                print(f"  Fallback API queries so far: {api_queries} …")
            qid = query_wikidata_for_qid(code)
            if not qid and root_code != code:
                qid = query_wikidata_for_qid(root_code)
            if qid:
                qid_cache[code] = qid  # cache for deduplication

        if qid:
            qids_found += 1
            coord_str = format_qs_coord(lat, lon)
            # QuickStatements format: QID TAB P625 TAB @LAT/LON
            qs_lines.append(f"{qid}\tP625\t{coord_str}")
        else:
            qids_not_found += 1

        # Always write CSV row (whether or not QID was found)
        csv_rows.append({
            "code":      code,
            "title":     title,
            "qid":       qid or "",
            "old_lat":   old_lat if old_lat is not None else "",
            "old_lon":   old_lon if old_lon is not None else "",
            "new_lat":   lat,
            "new_lon":   lon,
            "source":    source,
            "distance_m": dist_m if dist_m is not None else "",
            "notes":     notes,
        })

    # ── Save QuickStatements ──────────────────────────────────────────────────
    qs_path = DATA / "qs_coord_corrections.qs"
    with open(qs_path, "w", encoding="utf-8") as f:
        f.write("\n".join(qs_lines))
        if qs_lines:
            f.write("\n")
    print(f"\nSaved {len(qs_lines):,} QuickStatements lines -> {qs_path}")

    # ── Save CSV summary ──────────────────────────────────────────────────────
    csv_path = DATA / "coord_corrections_summary.csv"
    fieldnames = ["code", "title", "qid", "old_lat", "old_lon",
                  "new_lat", "new_lon", "source", "distance_m", "notes"]
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(csv_rows)
    print(f"Saved {len(csv_rows):,} rows -> {csv_path}")

    # ── Statistics ───────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("QID LOOKUP STATISTICS")
    print("=" * 60)
    print(f"Total corrections            : {len(corrections):,}")
    print(f"Fallback API queries made    : {api_queries:,}")
    print(f"QIDs resolved                : {qids_found:,}")
    print(f"QIDs not found               : {qids_not_found:,}")
    print(f"QuickStatements generated    : {len(qs_lines):,}")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
