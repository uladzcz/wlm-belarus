#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
harvest_wikivoyage_and_wikidata.py

Harvests external cultural heritage portal IDs (Globustut.by, Sobory.ru,
Radzima.org, Archivarta.by) and coordinates from ru.wikivoyage.org and Wikidata
SPARQL endpoint, merges them into a comprehensive lookup map, updates missing
coordinates in Belarusian monument catalogs, and produces a QuickStatements
batch for Sobory.ru (P8316).

Usage:
    python scripts/harvest_wikivoyage_and_wikidata.py [--refresh]
"""

import sys
import os
import json
import re
import time
import urllib.request
import urllib.parse
from pathlib import Path

# Ensure UTF-8 console output on Windows
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"

# File paths
WV_RAW_CACHE = DATA_DIR / "wikivoyage_raw_pages.json"
WD_SPARQL_CACHE = DATA_DIR / "wikidata_sparql_cache.json"
WD_P632_CACHE = DATA_DIR / "wikidata_p632_cache.json"
MONUMENTS_JSON = DATA_DIR / "monuments.json"
MONUMENTS_CORRECTED_JSON = DATA_DIR / "monuments_corrected.json"
HERITAGE_PORTALS_MAP = DATA_DIR / "heritage_portals_map.json"
QS_SOBORY_FILE = DATA_DIR / "qs_sobory_p8316.qs"

USER_AGENT = "WLM-Belarus-Integration/1.0 (https://github.com/uladzcz/wlm-belarus; contact: bafur@github)"

# Coordinate bounds for Belarus sanity checking
LAT_MIN, LAT_MAX = 51.2, 56.3
LON_MIN, LON_MAX = 23.1, 32.8


# ==============================================================================
# 1. Harvesting Wikivoyage
# ==============================================================================

def fetch_wikivoyage_pages(force_refresh=False):
    """
    Fetches all subpages under 'Культурное_наследие_Беларуси/' on ru.wikivoyage.org.
    Caches the downloaded pages to data/wikivoyage_raw_pages.json.
    """
    if not force_refresh and WV_RAW_CACHE.exists():
        print(f"[Wikivoyage] Loading cached pages from {WV_RAW_CACHE.name}...")
        with open(WV_RAW_CACHE, "r", encoding="utf-8") as f:
            return json.load(f)

    print("[Wikivoyage] Querying MediaWiki API for pages list...")
    prefix = "Культурное_наследие_Беларуси/"
    allpages_url = (
        "https://ru.wikivoyage.org/w/api.php?action=query&list=allpages"
        f"&apprefix={urllib.parse.quote(prefix)}&aplimit=500&format=json"
    )
    req = urllib.request.Request(allpages_url, headers={"User-Agent": USER_AGENT})
    resp = urllib.request.urlopen(req).read().decode("utf-8")
    data = json.loads(resp)
    titles = [p["title"] for p in data.get("query", {}).get("allpages", [])]
    print(f"[Wikivoyage] Found {len(titles)} subpages. Fetching contents in batches...")

    pages_dict = {}
    batch_size = 20
    for i in range(0, len(titles), batch_size):
        batch = titles[i : i + batch_size]
        post_data = urllib.parse.urlencode({
            "action": "query",
            "prop": "revisions",
            "rvprop": "content",
            "rvslots": "main",
            "titles": "|".join(batch),
            "format": "json"
        }).encode("utf-8")
        api_url = "https://ru.wikivoyage.org/w/api.php"
        r = urllib.request.Request(api_url, data=post_data, headers={"User-Agent": USER_AGENT})

        retries = 3
        while retries > 0:
            try:
                res = json.loads(urllib.request.urlopen(r, timeout=60).read().decode("utf-8"))
                for pid, p in res.get("query", {}).get("pages", {}).items():
                    title = p.get("title")
                    content = p.get("revisions", [{}])[0].get("slots", {}).get("main", {}).get("*", "")
                    pages_dict[title] = content
                break
            except Exception as e:
                print(f"  [Wikivoyage] Retry batch {i} due to: {e}")
                time.sleep(5)
                retries -= 1
        time.sleep(1.0)

    with open(WV_RAW_CACHE, "w", encoding="utf-8") as f:
        json.dump(pages_dict, f, ensure_ascii=False)
    print(f"[Wikivoyage] Successfully saved {len(pages_dict)} pages to {WV_RAW_CACHE.name}")
    return pages_dict


def extract_monument_templates(wikitext):
    """
    Extracts all {{Monument by | ...}} template strings from wikitext,
    correctly handling nested curly braces.
    """
    templates = []
    for match in re.finditer(r"\{\{\s*Monument\s+by\b", wikitext, re.IGNORECASE):
        start = match.start()
        depth = 0
        end = start
        for i in range(start, len(wikitext) - 1):
            if wikitext[i : i + 2] == "{{":
                depth += 1
            elif wikitext[i : i + 2] == "}}":
                depth -= 1
                if depth == 0:
                    end = i + 2
                    break
        templates.append(wikitext[start:end])
    return templates


def parse_template_params(tpl_text):
    """
    Parses key-value parameters from a {{Monument by | ...}} template,
    handling nested templates and wiki links.
    """
    content = tpl_text[2:-2]
    parts = content.split("|", 1)
    if len(parts) < 2:
        return {}
    params_str = parts[1]

    tokens = []
    start = 0
    depth_brace = 0
    depth_bracket = 0
    for i, ch in enumerate(params_str):
        if ch == "{":
            depth_brace += 1
        elif ch == "}":
            depth_brace -= 1
        elif ch == "[":
            depth_bracket += 1
        elif ch == "]":
            depth_bracket -= 1
        elif ch == "|" and depth_brace == 0 and depth_bracket == 0:
            tokens.append(params_str[start:i])
            start = i + 1
    tokens.append(params_str[start:])

    params = {}
    for t in tokens:
        if "=" in t:
            k, v = t.split("=", 1)
            # Remove comments <!-- ... -->
            v_clean = re.sub(r"<!--.*?-->", "", v, flags=re.DOTALL).strip()
            params[k.strip().lower()] = v_clean
    return params


def harvest_wikivoyage_monuments(pages_dict):
    """
    Parses all {{Monument by}} templates across all harvested Wikivoyage pages.
    Returns list of dicts with extracted fields:
    knid, wdid, globus, sobory, lat, long, image.
    """
    monuments = []
    for title, text in pages_dict.items():
        tpls = extract_monument_templates(text)
        for t in tpls:
            p = parse_template_params(t)
            knid = p.get("knid", "").strip()
            wdid = p.get("wdid", "").strip()
            globus = p.get("globus", "").strip()
            sobory = p.get("sobory", "").strip()
            lat_str = p.get("lat", "").strip()
            lon_str = (p.get("long") or p.get("lon") or "").strip()
            image = p.get("image", "").strip()
            image = re.sub(r"^(?:[Ff]ile|[Фф]айл):", "", image).strip()

            monuments.append({
                "knid": knid,
                "wdid": wdid,
                "globus": globus,
                "sobory": sobory,
                "lat": lat_str,
                "long": lon_str,
                "image": image,
                "_page": title
            })
    return monuments


# ==============================================================================
# 2. Harvesting Wikidata SPARQL
# ==============================================================================

def query_wikidata_sparql(force_refresh=False):
    """
    Queries Wikidata SPARQL endpoint for all Belarusian heritage monuments
    (P17=Q184 and (P632 or P11184 or P1435)).
    Extracts P632, P11184, P2488, P2491, P11671, P8316.
    """
    if not force_refresh and WD_SPARQL_CACHE.exists():
        print(f"[Wikidata] Loading cached SPARQL results from {WD_SPARQL_CACHE.name}...")
        with open(WD_SPARQL_CACHE, "r", encoding="utf-8") as f:
            return json.load(f)

    print("[Wikidata] Executing SPARQL query on query.wikidata.org...")
    sparql = """
    SELECT ?item ?p632 ?p11184 ?p2488 ?p2491 ?p11671 ?p8316 WHERE {
      ?item wdt:P17 wd:Q184 .
      { ?item wdt:P632 ?p632_init . } UNION { ?item wdt:P11184 ?p11184_init . } UNION { ?item wdt:P1435 ?p1435_init . }
      OPTIONAL { ?item wdt:P632 ?p632 . }
      OPTIONAL { ?item wdt:P11184 ?p11184 . }
      OPTIONAL { ?item wdt:P2488 ?p2488 . }
      OPTIONAL { ?item wdt:P2491 ?p2491 . }
      OPTIONAL { ?item wdt:P11671 ?p11671 . }
      OPTIONAL { ?item wdt:P8316 ?p8316 . }
    }
    """
    t0 = time.time()
    url = "https://query.wikidata.org/sparql?query=" + urllib.parse.quote(sparql) + "&format=json"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    resp = urllib.request.urlopen(req, timeout=120).read().decode("utf-8")
    data = json.loads(resp)
    bindings = data.get("results", {}).get("bindings", [])
    print(f"[Wikidata] Received {len(bindings)} bindings in {time.time()-t0:.2f}s.")

    with open(WD_SPARQL_CACHE, "w", encoding="utf-8") as f:
        json.dump(bindings, f, ensure_ascii=False)
    print(f"[Wikidata] Saved SPARQL results to {WD_SPARQL_CACHE.name}")
    return bindings


# ==============================================================================
# 3. Merging External Portals Map
# ==============================================================================

def build_heritage_portals_map(wv_monuments, sparql_bindings, p632_cache):
    """
    Merges all external heritage IDs and Wikidata QIDs into a unified map.
    Format:
    {
      "code_or_id": {
        "globus": "url_or_id",
        "radzima": "id",
        "sobory": "id",
        "archivarta": "id",
        "qid": "Q..."
      }
    }
    """
    portals_map = {}

    def get_or_create(key):
        if key not in portals_map:
            portals_map[key] = {}
        return portals_map[key]

    # Process Wikidata SPARQL bindings
    for b in sparql_bindings:
        qid = b["item"]["value"].split("/")[-1]
        code = b.get("p632", {}).get("value")
        slug = b.get("p11184", {}).get("value")
        key = code or slug or qid
        if not key:
            continue

        entry = get_or_create(key)
        if "qid" not in entry or not entry["qid"]:
            entry["qid"] = qid

        # Globus (P2488)
        if "p2488" in b and "globus" not in entry:
            entry["globus"] = b["p2488"]["value"]

        # Radzima (P2491): strip 'object/' prefix so ${id} works directly with template
        if "p2491" in b and "radzima" not in entry:
            rad_val = b["p2491"]["value"]
            rad_id = re.sub(r"^object/", "", rad_val)
            entry["radzima"] = rad_id

        # Archivarta (P11671)
        if "p11671" in b and "archivarta" not in entry:
            entry["archivarta"] = b["p11671"]["value"]

        # Sobory (P8316)
        if "p8316" in b and "sobory" not in entry:
            entry["sobory"] = b["p8316"]["value"]

    # Process Wikivoyage harvested monuments
    for m in wv_monuments:
        knid = m.get("knid")
        wdid = m.get("wdid")
        globus = m.get("globus")
        sobory = m.get("sobory")

        key = knid or wdid
        if not key:
            continue

        entry = get_or_create(key)

        if wdid and re.match(r"^Q\d+$", wdid) and "qid" not in entry:
            entry["qid"] = wdid

        if globus and "globus" not in entry:
            entry["globus"] = globus

        if sobory and "sobory" not in entry:
            entry["sobory"] = sobory

    # Supplement QIDs from local wikidata_p632_cache.json if not already present
    if p632_cache:
        for code, qid in p632_cache.items():
            if code in portals_map and "qid" not in portals_map[code]:
                portals_map[code]["qid"] = qid

    # Filter out entries that have neither portal links nor QID (if any)
    cleaned_map = {}
    for k, v in portals_map.items():
        if any(f in v for f in ["globus", "radzima", "sobory", "archivarta", "qid"]):
            cleaned_map[k] = v

    return cleaned_map


# ==============================================================================
# 4. Updating Missing Coordinates from Wikivoyage
# ==============================================================================

def update_missing_coordinates(wv_monuments):
    """
    For monuments in data/monuments.json where lat is null or 0:
    Checks if Wikivoyage has valid lat and long within Belarus bounds.
    Updates data/monuments.json and data/monuments_corrected.json.
    Returns the count of updated monuments.
    """
    if not MONUMENTS_JSON.exists():
        print(f"[Coordinates] Error: {MONUMENTS_JSON.name} does not exist.")
        return 0

    with open(MONUMENTS_JSON, "r", encoding="utf-8") as f:
        monuments = json.load(f)

    # Index Wikivoyage coordinates by exact knid and base knid
    wv_coords = {}
    for m in wv_monuments:
        knid = m.get("knid")
        if not knid:
            continue
        lat_str = m.get("lat")
        lon_str = m.get("long")
        if lat_str and lon_str:
            try:
                lat = float(lat_str)
                lon = float(lon_str)
                if LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX:
                    wv_coords[knid] = (lat, lon)
                    base_knid = knid.split("-")[0]
                    if base_knid not in wv_coords:
                        wv_coords[base_knid] = (lat, lon)
            except ValueError:
                continue

    updated_count = 0
    for m in monuments:
        curr_lat = m.get("lat")
        curr_lon = m.get("lon")
        if curr_lat is None or curr_lat == 0 or curr_lon is None or curr_lon == 0:
            code = m.get("c")
            if code and code in wv_coords:
                new_lat, new_lon = wv_coords[code]
                m["lat"] = round(new_lat, 6)
                m["lon"] = round(new_lon, 6)
                updated_count += 1

    # Save to data/monuments.json
    with open(MONUMENTS_JSON, "w", encoding="utf-8") as f:
        json.dump(monuments, f, ensure_ascii=False, indent=2)

    # Also save to data/monuments_corrected.json
    with open(MONUMENTS_CORRECTED_JSON, "w", encoding="utf-8") as f:
        json.dump(monuments, f, ensure_ascii=False, indent=2)

    return updated_count


# ==============================================================================
# 5. QuickStatements Batch for Sobory.ru (P8316)
# ==============================================================================

def generate_sobory_qs_batch(wv_monuments, p632_cache, portals_map):
    """
    For all items that have both a known Wikidata QID (from Wikivoyage wdid,
    wikidata_p632_cache.json, or portals_map) and a sobory ID:
    Generates QuickStatements line: QID\tP8316\t"SOBORY_ID"
    Saves to data/qs_sobory_p8316.qs.
    Returns list of generated statement lines.
    """
    statements = []
    seen_pairs = set()

    for m in wv_monuments:
        sobory_id = m.get("sobory")
        if not sobory_id:
            continue

        qid = None
        # Check direct wdid
        wdid = m.get("wdid")
        if wdid and re.match(r"^Q\d+$", wdid):
            qid = wdid

        # Check p632_cache or base knid
        knid = m.get("knid")
        if not qid and knid:
            if knid in p632_cache:
                qid = p632_cache[knid]
            elif knid.split("-")[0] in p632_cache:
                qid = p632_cache[knid.split("-")[0]]

        # Check portals_map fallback
        if not qid and knid and knid in portals_map:
            qid = portals_map[knid].get("qid")

        if qid and re.match(r"^Q\d+$", qid):
            pair = (qid, sobory_id)
            if pair not in seen_pairs:
                seen_pairs.add(pair)
                statements.append(f'{qid}\tP8316\t"{sobory_id}"')

    # Save to data/qs_sobory_p8316.qs
    with open(QS_SOBORY_FILE, "w", encoding="utf-8") as f:
        f.write("/* QuickStatements batch: Sobory.ru IDs (P8316) for Belarusian heritage */\n")
        for line in statements:
            f.write(line + "\n")

    return statements


# ==============================================================================
# Main Execution Pipeline
# ==============================================================================

def main():
    force_refresh = "--refresh" in sys.argv

    print("=" * 70)
    print("BELARUSIAN HERITAGE HARVESTER: WIKIVOYAGE & WIKIDATA INTEGRATION")
    print("=" * 70)

    # 1. Harvest Wikivoyage
    pages_dict = fetch_wikivoyage_pages(force_refresh=force_refresh)
    wv_monuments = harvest_wikivoyage_monuments(pages_dict)
    print(f"\n[Wikivoyage Summary]")
    print(f"  Total pages processed: {len(pages_dict)}")
    print(f"  Total {{Monument by}} templates parsed: {len(wv_monuments)}")
    print(f"  With knid: {sum(1 for m in wv_monuments if m.get('knid'))}")
    print(f"  With wdid: {sum(1 for m in wv_monuments if m.get('wdid'))}")
    print(f"  With globus: {sum(1 for m in wv_monuments if m.get('globus'))}")
    print(f"  With sobory: {sum(1 for m in wv_monuments if m.get('sobory'))}")
    print(f"  With coords: {sum(1 for m in wv_monuments if m.get('lat') and m.get('long'))}")
    print(f"  With image:  {sum(1 for m in wv_monuments if m.get('image'))}")

    # 2. Harvest Wikidata SPARQL
    sparql_bindings = query_wikidata_sparql(force_refresh=force_refresh)
    print(f"\n[Wikidata Summary]")
    print(f"  Total SPARQL result rows: {len(sparql_bindings)}")

    # Load P632 cache
    p632_cache = {}
    if WD_P632_CACHE.exists():
        with open(WD_P632_CACHE, "r", encoding="utf-8") as f:
            p632_cache = json.load(f)
        print(f"  Loaded {len(p632_cache)} entries from {WD_P632_CACHE.name}")

    # 3. Build and save heritage_portals_map.json
    print("\n[Merge] Building comprehensive heritage portals map...")
    portals_map = build_heritage_portals_map(wv_monuments, sparql_bindings, p632_cache)
    with open(HERITAGE_PORTALS_MAP, "w", encoding="utf-8") as f:
        json.dump(portals_map, f, ensure_ascii=False, indent=2)

    globus_cnt = sum(1 for v in portals_map.values() if "globus" in v)
    radzima_cnt = sum(1 for v in portals_map.values() if "radzima" in v)
    sobory_cnt = sum(1 for v in portals_map.values() if "sobory" in v)
    archivarta_cnt = sum(1 for v in portals_map.values() if "archivarta" in v)
    qid_cnt = sum(1 for v in portals_map.values() if "qid" in v)
    any_portal_cnt = sum(1 for v in portals_map.values() if any(k in v for k in ["globus", "radzima", "sobory", "archivarta"]))

    print(f"  Saved {len(portals_map)} entries to {HERITAGE_PORTALS_MAP.name}")
    print(f"  Entries with at least one external portal: {any_portal_cnt}")
    print(f"    - Globustut (globus): {globus_cnt}")
    print(f"    - Radzima.org (radzima): {radzima_cnt}")
    print(f"    - Sobory.ru (sobory): {sobory_cnt}")
    print(f"    - Archivarta (archivarta): {archivarta_cnt}")
    print(f"    - Wikidata QID (qid): {qid_cnt}")

    # 4. Update missing coordinates in monuments.json & monuments_corrected.json
    print("\n[Coordinates] Updating missing coordinates from Wikivoyage...")
    updated_coords = update_missing_coordinates(wv_monuments)
    print(f"  Updated {updated_coords} monuments with new valid Wikivoyage coordinates.")
    print(f"  Saved updates to {MONUMENTS_JSON.name} and {MONUMENTS_CORRECTED_JSON.name}")

    # 5. Generate QuickStatements batch for Sobory.ru (P8316)
    print("\n[QuickStatements] Generating Sobory.ru (P8316) batch...")
    qs_statements = generate_sobory_qs_batch(wv_monuments, p632_cache, portals_map)
    print(f"  Generated {len(qs_statements)} QS statements in {QS_SOBORY_FILE.name}")
    print(f"  Sample statement: {qs_statements[0] if qs_statements else 'None'}")

    # 6. Verification
    print("\n" + "=" * 70)
    print("OUTPUT FILES VERIFICATION")
    print("=" * 70)
    files_to_check = [
        HERITAGE_PORTALS_MAP,
        MONUMENTS_JSON,
        MONUMENTS_CORRECTED_JSON,
        QS_SOBORY_FILE
    ]
    all_ok = True
    for fp in files_to_check:
        if fp.exists():
            size_kb = fp.stat().st_size / 1024
            print(f"  [OK] {fp.name} exists ({size_kb:.1f} KB)")
        else:
            print(f"  [FAIL] {fp.name} DOES NOT exist!")
            all_ok = False

    if all_ok:
        print("\nAll tasks completed successfully!")
    else:
        print("\nSome output files are missing. Please check errors above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
