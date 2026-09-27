#!/usr/bin/env python3
"""
geocode_urban_addresses.py
==========================
Geocode urban Belarusian monuments with explicit street addresses using OpenStreetMap / Nominatim.

Identifies fake coordinate clusters in heritage.gov.by catalog (e.g. 9 buildings in Grodno
historical center dumped onto Ulica Strycharska in Dzeviatau-ka, or 64 buildings dumped at a single point),
extracts exact street addresses, queries Nominatim with rate-limiting and structured fallback queries,
matches building polygons/points, computes distance discrepancy in meters, and saves output to
data/matched_osm_addresses.json.
"""

import os
import sys
import json
import time
import math
import re
import argparse
import urllib.request
import urllib.parse
from collections import Counter

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
MONUMENTS_FILE = os.path.join(DATA_DIR, "monuments.json")
OUTPUT_FILE = os.path.join(DATA_DIR, "matched_osm_addresses.json")
CACHE_FILE = os.path.join(DATA_DIR, ".nominatim_cache.json")

USER_AGENT = "AntigravityHeritageBelarus/1.0 (urban geocoding architectural heritage; contact: bafur@users.noreply.github.com)"

# Regex patterns for street addresses in Belarusian
PREFIX_RE = re.compile(
    r'(?:вул\.|вуліца|пер\.|зав\.|завулак|пр\.|прасп\.|праспект|пл\.|плошча|бул\.|бульвар|тракт|спуск|праезд|узвоз)\s+'
    r'([А-Яа-яЁёІіЎўA-Za-z0-9\s\-\.\'\’]+?)(?:,\s*|\s+(?:д\.|дом\s*)?|,\s*д\.\s*)'
    r'(\d+[а-яА-Яa-zA-Z\/\d\-]*)',
    re.IGNORECASE
)

POSTFIX_RE = re.compile(
    r'([А-Яа-яЁёІіЎўA-Za-z0-9\s\-\.\'\’]+?)\s+'
    r'(?:вул\.|вуліца|пер\.|зав\.|завулак|пр\.|прасп\.|праспект|пл\.|плошча|бул\.|бульвар|тракт|спуск|праезд|узвоз)'
    r'(?:,\s*|\s+(?:д\.|дом\s*)?|,\s*д\.\s*)'
    r'(\d+[а-яА-Яa-zA-Z\/\d\-]*)',
    re.IGNORECASE
)

STREET_EXPANSIONS = {
    'К. Маркса': 'Карла Маркса',
    'К.Маркса': 'Карла Маркса',
    'М. Багдановіча': 'Максіма Багдановіча',
    'М.Багдановіча': 'Максіма Багдановіча',
    'Багдановіча М': 'Максіма Багдановіча',
    'Ніжнепакроўская': 'Ніжне-Пакроўская',
    'Ф. Скарыны': 'Францыска Скарыны',
    'Я. Коласа': 'Якуба Коласа',
    'Я. Купалы': 'Янкі Купалы',
}

def haversine_distance(lat1, lon1, lat2, lon2):
    """Compute great-circle distance between two points on Earth in meters."""
    R = 6371000.0  # Earth radius in meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2.0)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0)**2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c

def clean_settlement(loc):
    """Clean settlement name by removing prefixes like г., г.п., аг., etc."""
    if not loc:
        return ""
    cleaned = re.sub(r'^(?:г\.|г\.п\.|аг\.|аграгарадок|в\.|пас\.)\s*', '', loc.strip())
    # remove trailing district notes if any
    cleaned = cleaned.split(',')[0].strip()
    return cleaned

def parse_address(monument):
    """
    Extract street name and house number from address field or title.
    Returns (street, house, raw_match) or (None, None, None).
    """
    text = ' ' + (monument.get('a') or '') + ' ' + (monument.get('t') or '')
    match = PREFIX_RE.search(text)
    if not match:
        match = POSTFIX_RE.search(text)
    if match:
        street = match.group(1).strip(" ,.-'\"")
        house = match.group(2).strip(" ,.-'\"")
        if street in STREET_EXPANSIONS:
            street = STREET_EXPANSIONS[street]
        # Sanity check: street shouldn't be too long or empty
        if street and len(street) < 50 and house:
            return street, house, match.group(0).strip()
    return None, None, None

class NominatimGeocoder:
    def __init__(self, cache_path=CACHE_FILE, delay=1.05):
        self.cache_path = cache_path
        self.delay = delay
        self.last_query_time = 0.0
        self.cache = self._load_cache()

    def _load_cache(self):
        if os.path.exists(self.cache_path):
            try:
                with open(self.cache_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Warning: could not load cache ({e}), starting empty.")
        return {}

    def _save_cache(self):
        try:
            with open(self.cache_path, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Warning: could not save cache: {e}")

    def _rate_limit(self):
        elapsed = time.time() - self.last_query_time
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self.last_query_time = time.time()

    def _request(self, params):
        self._rate_limit()
        params['format'] = 'jsonv2'
        params['addressdetails'] = 1
        params['accept-language'] = 'be,ru,en'
        url = f"https://nominatim.openstreetmap.org/search?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    return json.loads(resp.read().decode('utf-8'))
            except Exception as e:
                if attempt < 2:
                    time.sleep(2.0 * (attempt + 1))
                else:
                    print(f"  [HTTP Error] {e} for {url}")
        return []

    def _is_valid_match(self, result, target_house):
        """
        Check if Nominatim result corresponds to a building/address matching target_house.
        """
        target_norm = target_house.lower().strip()
        addr = result.get('address', {})
        h_osm = addr.get('house_number', '').lower().strip()
        cls = result.get('category') or result.get('class', '')
        osm_type = result.get('type', '')
        disp = result.get('display_name', '')

        # 1. Exact or normalized house match
        if h_osm:
            if h_osm == target_norm:
                return True
            # Prefix matches like 34A vs 34, or 67/1 vs 67
            if target_norm in h_osm or h_osm in target_norm:
                return True

        # 2. Building/amenity/tourism/historic match where house appears in display_name or address
        if cls in ('building', 'amenity', 'tourism', 'historic', 'office', 'shop', 'leisure'):
            # If target house number is explicitly in the display name
            pattern = r'\b' + re.escape(target_house) + r'\b'
            if re.search(pattern, disp, re.IGNORECASE):
                return True

        # 3. OSM place=house or place=address
        if cls == 'place' and osm_type in ('house', 'address'):
            if target_norm in disp.lower():
                return True

        return False

    def geocode(self, city, street, house):
        cache_key = f"{city}|{street}|{house}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        clean_c = clean_settlement(city)
        match = None

        # Strategy 1: Structured query (street, city, country)
        structured_params = {
            'street': f"{street} {house}",
            'city': clean_c,
            'country': 'Беларусь',
            'limit': 5
        }
        res = self._request(structured_params)
        for r in res:
            if self._is_valid_match(r, house):
                match = r
                break

        # Strategy 2: Freeform query (street house, city, Беларусь)
        if not match:
            freeform_params = {
                'q': f"{street} {house}, {clean_c}, Беларусь",
                'limit': 5
            }
            res = self._request(freeform_params)
            for r in res:
                if self._is_valid_match(r, house):
                    match = r
                    break

        # Strategy 3: Base house number if house contains slash or letter (e.g. 34А -> 34, 79/1 -> 79)
        if not match:
            base_house = re.match(r'^(\d+)', house)
            if base_house and base_house.group(1) != house:
                base_num = base_house.group(1)
                structured_base = {
                    'street': f"{street} {base_num}",
                    'city': clean_c,
                    'country': 'Беларусь',
                    'limit': 5
                }
                res = self._request(structured_base)
                for r in res:
                    if self._is_valid_match(r, base_num):
                        match = r
                        break

        # Record in cache
        if match:
            stored = {
                'status': 'matched',
                'lat': float(match['lat']),
                'lon': float(match['lon']),
                'place_id': match.get('place_id'),
                'osm_type': match.get('osm_type'),
                'osm_id': match.get('osm_id'),
                'osm_class': match.get('category') or match.get('class'),
                'osm_type_detail': match.get('type'),
                'display_name': match.get('display_name'),
                'address_details': match.get('address')
            }
        else:
            stored = {'status': 'not_found'}

        self.cache[cache_key] = stored
        self._save_cache()
        return stored


def main():
    parser = argparse.ArgumentParser(description="Geocode urban monuments with explicit addresses")
    parser.add_argument("--min-cluster-size", type=int, default=4, help="Min monuments sharing exact coords to flag as cluster (default: 4)")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of queries to geocode")
    parser.add_argument("--code", type=str, default=None, help="Geocode a specific monument by heritage code")
    args = parser.parse_args()

    print("=" * 70)
    print("BELARUSIAN HERITAGE URBAN ADDRESS GEOCODING (OSM / Nominatim)")
    print("=" * 70)

    # 1. Load monuments
    print(f"Loading monuments from: {MONUMENTS_FILE}")
    with open(MONUMENTS_FILE, 'r', encoding='utf-8') as f:
        monuments = json.load(f)
    print(f"Loaded {len(monuments)} monuments.")

    # 2. Identify suspicious coordinate clusters
    coord_counter = Counter((round(m['lat'], 6), round(m['lon'], 6)) for m in monuments if m.get('lat') and m.get('lon'))
    cluster_coords = {c: count for c, count in coord_counter.items() if count >= args.min_cluster_size}
    print(f"\nSuspicious coordinate clusters (size >= {args.min_cluster_size}): {len(cluster_coords)} clusters")
    total_cluster_monuments = sum(cluster_coords.values())
    print(f"Total monuments inside suspicious clusters: {total_cluster_monuments}")

    # 3. Identify monuments with explicit addresses
    all_with_address = []
    cluster_with_address = []

    for m in monuments:
        street, house, raw = parse_address(m)
        if street and house:
            m_copy = dict(m)
            m_copy['parsed_street'] = street
            m_copy['parsed_house'] = house
            m_copy['raw_address_match'] = raw
            all_with_address.append(m_copy)

            coord = (round(m.get('lat', 0), 6), round(m.get('lon', 0), 6))
            if coord in cluster_coords:
                cluster_with_address.append(m_copy)

    print(f"All catalog monuments with parsed street + house: {len(all_with_address)}")
    print(f"Cluster monuments with parsed street + house: {len(cluster_with_address)}")

    # Target selection
    if args.code:
        targets = [m for m in all_with_address if m.get('c') == args.code]
        print(f"Targeting single code: {args.code} (found {len(targets)})")
    else:
        # Default: target cluster monuments with explicit addresses
        targets = cluster_with_address

    if args.limit:
        targets = targets[:args.limit]
        print(f"Limiting to first {args.limit} monuments.")

    print(f"\nTotal targets to process: {len(targets)}")

    # Group unique queries
    unique_queries = {}
    for m in targets:
        loc = m.get('loc') or m.get('dst') or ''
        key = (loc, m['parsed_street'], m['parsed_house'])
        if key not in unique_queries:
            unique_queries[key] = []
        unique_queries[key].append(m)

    print(f"Unique geocoding queries needed: {len(unique_queries)}")

    # 4. Geocode using Nominatim
    geocoder = NominatimGeocoder(cache_path=CACHE_FILE, delay=1.05)

    matches_by_code = {}
    city_stats = Counter()
    discrepancies = []

    print("\nStarting Nominatim geocoding...")
    start_time = time.time()

    for idx, ((loc, street, house), mon_list) in enumerate(unique_queries.items(), 1):
        res = geocoder.geocode(loc, street, house)
        status = res.get('status')
        elapsed = time.time() - start_time

        if status == 'matched':
            new_lat = res['lat']
            new_lon = res['lon']
            for m in mon_list:
                orig_lat = m.get('lat', 0.0)
                orig_lon = m.get('lon', 0.0)
                dist_m = haversine_distance(orig_lat, orig_lon, new_lat, new_lon)
                discrepancies.append(dist_m)
                city_name = clean_settlement(loc) or 'Unknown'
                city_stats[city_name] += 1

                record = {
                    'code': m.get('c'),
                    'id': m.get('id'),
                    'title': m.get('t'),
                    'settlement': m.get('loc'),
                    'raw_address': m.get('a'),
                    'parsed_street': street,
                    'parsed_house': house,
                    'original_coords': {'lat': orig_lat, 'lon': orig_lon},
                    'osm_coords': {'lat': new_lat, 'lon': new_lon},
                    'distance_discrepancy_m': round(dist_m, 1),
                    'osm_place_id': res.get('place_id'),
                    'osm_type': res.get('osm_type'),
                    'osm_id': res.get('osm_id'),
                    'osm_class': res.get('osm_class'),
                    'osm_type_detail': res.get('osm_type_detail'),
                    'display_name': res.get('display_name')
                }
                matches_by_code[m.get('c')] = record

            print(f"[{idx}/{len(unique_queries)}] ({elapsed:.1f}s) MATCH: {loc} | {street}, {house} -> "
                  f"({new_lat:.6f}, {new_lon:.6f}) [disp: {dist_m:.0f}m, items: {len(mon_list)}]")
        else:
            print(f"[{idx}/{len(unique_queries)}] ({elapsed:.1f}s) NOT FOUND: {loc} | {street}, {house}")

    # 5. Save output
    avg_dist = sum(discrepancies) / len(discrepancies) if discrepancies else 0.0
    median_dist = sorted(discrepancies)[len(discrepancies) // 2] if discrepancies else 0.0
    max_dist = max(discrepancies) if discrepancies else 0.0

    output_data = {
        'metadata': {
            'generated_at': time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            'geocoder': 'OpenStreetMap Nominatim',
            'user_agent': USER_AGENT,
            'rate_limit_delay_sec': 1.05
        },
        'statistics': {
            'total_catalog_monuments': len(monuments),
            'suspicious_clusters_detected': len(cluster_coords),
            'monuments_in_suspicious_clusters': total_cluster_monuments,
            'cluster_monuments_with_parsed_address': len(cluster_with_address),
            'unique_queries_executed': len(unique_queries),
            'matched_monuments_count': len(matches_by_code),
            'match_rate_pct': round((len(matches_by_code) / len(targets) * 100), 1) if targets else 0.0,
            'average_distance_improvement_m': round(avg_dist, 1),
            'median_distance_improvement_m': round(median_dist, 1),
            'max_distance_discrepancy_m': round(max_dist, 1),
            'matches_by_settlement': dict(city_stats.most_common())
        },
        'matches': matches_by_code
    }

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    print(f"\nSaved results to: {OUTPUT_FILE}")

    # 6. Validate key cases
    key_codes = ['413Г000659', '413Г000778', '412Г000665_16']
    print("\n" + "=" * 70)
    print("KEY CASES VALIDATION (GRODNO):")
    print("=" * 70)
    for kc in key_codes:
        if kc in matches_by_code:
            m = matches_by_code[kc]
            print(f"[OK] {kc}: {m['title']}")
            print(f"     Address: {m['parsed_street']}, {m['parsed_house']}")
            print(f"     Original Coords: ({m['original_coords']['lat']:.6f}, {m['original_coords']['lon']:.6f})")
            print(f"     OSM Match Coords: ({m['osm_coords']['lat']:.6f}, {m['osm_coords']['lon']:.6f})")
            print(f"     Discrepancy: {m['distance_discrepancy_m']} m")
            print(f"     OSM: {m['osm_type']} #{m['osm_id']} ({m['osm_class']}:{m['osm_type_detail']})")
            print(f"     Display: {m['display_name']}")
        else:
            print(f"[FAIL] Key case {kc} NOT found in matches!")

    # 7. Summary Report
    print("\n" + "=" * 70)
    print("FINAL SUMMARY STATISTICS:")
    print("=" * 70)
    print(f"Total Monuments Processed: {len(targets)}")
    print(f"Total Unique Queries: {len(unique_queries)}")
    print(f"Total Addresses Successfully Matched: {len(matches_by_code)}")
    print(f"Match Success Rate: {output_data['statistics']['match_rate_pct']}%")
    print(f"Average Discrepancy / Improvement: {avg_dist:.1f} meters")
    print(f"Median Discrepancy / Improvement:  {median_dist:.1f} meters")
    print(f"Maximum Discrepancy Corrected:    {max_dist:.1f} meters")
    print("\nTop Settlements Fixed:")
    for city, count in city_stats.most_common(10):
        print(f"  {city:20s}: {count} monuments corrected")
    print("=" * 70)

if __name__ == "__main__":
    main()
