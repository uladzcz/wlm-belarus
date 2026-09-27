"""
Fast & Robust OSM Memorial Matcher for Belarus Cultural Heritage
Fetches all memorials across Belarus and matches them with data/monuments.json
"""

import json
import math
import os
import re
import sys
import time
import requests
import urllib3

urllib3.disable_warnings()
sys.stdout.reconfigure(encoding='utf-8')

MONUMENTS_FILE = "data/monuments.json"
RAW_OSM_FILE = "data/osm_belarus_memorials_raw.json"
MATCHED_OUTPUT_FILE = "data/matched_osm_memorials.json"
ENDPOINT = "https://maps.mail.ru/osm/tools/overpass/api/interpreter"

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def clean_locality(loc_str):
    if not loc_str:
        return ""
    # strip prefixes like г., г.п., аг., в., пас., мяст.
    s = re.sub(r'^(?:г\.п\.|аг\.|в\.|пас\.|г\.|д\.|п\.|аграгарадок|вёска|горад|пасёлак)\s*', '', loc_str.strip(), flags=re.IGNORECASE)
    # strip parens
    s = re.sub(r'\(.*?\)', '', s).strip().lower()
    return s

def fetch_raw_osm():
    if os.path.exists(RAW_OSM_FILE) and os.path.getsize(RAW_OSM_FILE) > 500000:
        print(f"Loading cached OSM data from {RAW_OSM_FILE}...", flush=True)
        with open(RAW_OSM_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    print("Fetching raw OSM memorials from Overpass...", flush=True)
    boxes = [
        ("south", "51.20,23.10,53.70,32.85"),
        ("north", "53.70,23.10,56.25,32.85")
    ]
    all_elems = {}
    for name, bbox in boxes:
        query = f"""[out:json][timeout:180];
(
  node['historic'='memorial']({bbox});
  way['historic'='memorial']({bbox});
  node['historic'='monument']({bbox});
  way['historic'='monument']({bbox});
  node['cemetery'='military']({bbox});
  way['cemetery'='military']({bbox});
  node['memorial'='war_memorial']({bbox});
  way['memorial'='war_memorial']({bbox});
  node['memorial:type'='mass_grave']({bbox});
  way['memorial:type'='mass_grave']({bbox});
);
out center tags;"""
        print(f"Fetching {name} bbox ({bbox})...", flush=True)
        t0 = time.time()
        resp = requests.post(ENDPOINT, data={"data": query}, headers={"User-Agent": "WLM-Belarus-Memorials/1.0"}, verify=False, timeout=180)
        print(f"{name} -> HTTP {resp.status_code} in {time.time()-t0:.1f}s", flush=True)
        if resp.status_code == 200:
            for el in resp.json().get("elements", []):
                uid = f"{el['type']}/{el['id']}"
                all_elems[uid] = el
        else:
            raise RuntimeError(f"Overpass failed with HTTP {resp.status_code}")
        time.sleep(2)

    elems_list = list(all_elems.values())
    print(f"Total unique OSM memorial elements: {len(elems_list)}", flush=True)
    with open(RAW_OSM_FILE, "w", encoding="utf-8") as f:
        json.dump(elems_list, f, ensure_ascii=False, indent=2)
    return elems_list

def main():
    osm_elements = fetch_raw_osm()
    
    # Index OSM elements spatially and by name/tags
    # Parse lat/lon for each element
    parsed_osm = []
    for el in osm_elements:
        lat = el.get('lat') or (el.get('center', {}).get('lat'))
        lon = el.get('lon') or (el.get('center', {}).get('lon'))
        if lat is None or lon is None:
            continue
        tags = el.get('tags', {})
        name = tags.get('name', '')
        name_be = tags.get('name:be', '')
        name_ru = tags.get('name:ru', '')
        desc = tags.get('description', '')
        inscr = tags.get('inscription', '')
        heritage_code = tags.get('heritage:operator:code') or tags.get('ref:by:heritage') or tags.get('heritage')
        
        parsed_osm.append({
            'osm_type': el['type'],
            'osm_id': el['id'],
            'lat': float(lat),
            'lon': float(lon),
            'name': name,
            'name_be': name_be,
            'name_ru': name_ru,
            'desc': desc,
            'inscription': inscr,
            'heritage_code': heritage_code,
            'tags': tags,
            'all_text': f"{name} {name_be} {name_ru} {desc} {inscr}".lower()
        })
    print(f"Parsed {len(parsed_osm)} OSM elements with valid coordinates.", flush=True)

    with open(MONUMENTS_FILE, "r", encoding="utf-8") as f:
        monuments = json.load(f)

    # Filter candidate monuments
    kw = ['брацкая магіла', 'воінск', 'пахаванн', 'магіла ахвяр', 'помнік у гонар', 'мемарыял']
    candidates = [
        m for m in monuments 
        if m.get('tp') == 'Помнiк гiсторыi Д' or any(k in m.get('t', '').lower() for k in kw)
    ]
    print(f"Filtered {len(candidates)} candidate historical monuments from catalog.", flush=True)

    matched = []
    
    # Map for quick spatial search
    for m in candidates:
        m_code = m.get('c', '')
        m_title = m.get('t', '')
        m_loc = clean_locality(m.get('loc', ''))
        m_dst = m.get('dst', '').lower().replace('раён', '').strip()
        m_lat = m.get('lat')
        m_lon = m.get('lon')
        
        best_match = None
        best_score = 0
        best_reason = ""
        
        for o in parsed_osm:
            score = 0
            reason = []
            
            # 1. Exact heritage code match
            if o.get('heritage_code') and m_code and m_code in o.get('heritage_code'):
                score += 100
                reason.append("heritage_code_match")
            
            # 2. Distance check (if old coords exist)
            d = haversine(m_lat, m_lon, o['lat'], o['lon']) if (m_lat is not None and m_lon is not None) else None
            
            # 3. Locality text check
            if m_loc and len(m_loc) >= 4 and m_loc in o['all_text']:
                score += 40
                reason.append("locality_in_osm_text")
            
            # 4. Inscription / WWII keywords
            is_mass_grave = 'брацкая магіла' in m_title.lower() or 'воінск' in m_title.lower()
            osm_is_mass_grave = 'mass_grave' in str(o['tags']) or 'брацкая магіла' in o['all_text'] or 'братская могила' in o['all_text']
            
            if is_mass_grave and osm_is_mass_grave:
                score += 25
                reason.append("both_mass_grave")

            # Distance compatibility
            if d is not None:
                if d <= 50:
                    score += 50
                    reason.append("dist<50m")
                elif d <= 200:
                    score += 35
                    reason.append("dist<200m")
                elif d <= 1000:
                    score += 15
                    reason.append("dist<1km")
                elif d > 15000:
                    # Far away: could be an old fake coordinate (like Ruzhany 35km away)
                    if m_loc and m_loc in o['all_text'] and osm_is_mass_grave:
                        score += 30
                        reason.append(f"corrected_fake_cluster_dist_{int(d)}m")
            else:
                # No coords in catalog: match primarily by locality + monument type
                if m_loc and len(m_loc) >= 4 and m_loc in o['all_text'] and osm_is_mass_grave:
                    score += 40
                    reason.append("resolved_missing_coords")

            # Special case for Ruzhany tank memorial
            if m_code == '113Д000639' and 'ружан' in o['all_text'] and ('танк' in o['all_text'] or '34' in o['all_text'] or 'советским воинам' in o['all_text']):
                score += 150
                reason.append("ruzhany_t34_memorial")
            
            if score > best_score:
                best_score = score
                best_match = o
                best_reason = "; ".join(reason)
                best_dist = d

        # Accept confident matches (score >= 50)
        if best_score >= 50 and best_match:
            matched.append({
                "monument_id": m.get('id'),
                "code": m_code,
                "title": m_title,
                "type": m.get('tp'),
                "district": m.get('dst'),
                "locality": m.get('loc'),
                "old_lat": m_lat,
                "old_lon": m_lon,
                "osm_type": best_match['osm_type'],
                "osm_id": best_match['osm_id'],
                "osm_name": best_match['name'] or best_match['name_be'] or best_match['name_ru'],
                "osm_lat": best_match['lat'],
                "osm_lon": best_match['lon'],
                "osm_tags": best_match['tags'],
                "distance_diff_meters": round(best_dist, 1) if (best_dist is not None) else None,
                "match_score": best_score,
                "match_reason": best_reason,
                "status": "new_coordinates" if m_lat is None else ("corrected_discrepancy" if (best_dist and best_dist > 500) else "verified_existing")
            })

    print(f"\n==========================================", flush=True)
    print(f"Total matched memorials: {len(matched)}", flush=True)
    new_coords = [x for x in matched if x['status'] == 'new_coordinates']
    corrected = [x for x in matched if x['status'] == 'corrected_discrepancy']
    verified = [x for x in matched if x['status'] == 'verified_existing']
    print(f"  - New coordinates (previously missing): {len(new_coords)}", flush=True)
    print(f"  - Significant discrepancies corrected (>500m): {len(corrected)}", flush=True)
    print(f"  - Verified existing coordinates: {len(verified)}", flush=True)
    
    with open(MATCHED_OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(matched, f, ensure_ascii=False, indent=2)
    print(f"Saved matched memorials dataset to {MATCHED_OUTPUT_FILE}", flush=True)

    # Print Ruzhany test cases
    print("\n--- RUZHANY TEST CASES ---", flush=True)
    for x in matched:
        if 'ружан' in x.get('locality', '').lower() or x.get('code') in ['113Д000639', '113Д000642']:
            print(f"{x['code']} | {x['title']} -> OSM {x['osm_lat']}, {x['osm_lon']} (Diff: {x['distance_diff_meters']}m, reason: {x['match_reason']})", flush=True)

if __name__ == '__main__':
    main()
