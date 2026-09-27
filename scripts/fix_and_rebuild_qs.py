"""
Fix and regenerate QuickStatements for coordinate corrections.
Also adds Trostenets to corrections (flagged_large_diameter=True but primary site is known).
Also deduplicates QS lines.
"""
import json, sys, csv
sys.stdout.reconfigure(encoding='utf-8')

# Load data
cc = json.load(open('data/coords_corrected.json', encoding='utf-8'))
pz = json.load(open('data/pravo_heritage_protection_zones_v2.json', encoding='utf-8'))
wd_cache = json.load(open('data/wikidata_p632_cache.json', encoding='utf-8'))

# Add Trostenets manually (flagged_large_diameter=True but primary site is correct)
# Primary monument territory (Gate of Memory, pts 1-36) at 53.838652, 27.70534
trostenets_code = '711Д000283'
if not any(x['code'] == trostenets_code for x in cc):
    cc.append({
        'code': trostenets_code,
        'lat': 53.838652,
        'lon': 27.70534,
        'old_lat': None,
        'old_lon': None,
        'source': 'pravo_new',
        'confidence': 'high',
        'distance_corrected_m': None,
        'notes': 'Primary memorial territory (Brама Памяці/Gate of Memory, pts 1-36). Blagovshchina pits (pts 40-47) at 53.842739,27.7411 archived as secondary.',
        'priority': 'P2'
    })
    print(f'Added Trostenets {trostenets_code} to corrections.')

# Build QID lookup from cache
# Cache is a dict mapping heritage code -> QID string directly
if isinstance(wd_cache, dict):
    code_to_qid = wd_cache  # already in the right format: {"413Г000659": "Q12345", ...}
else:
    code_to_qid = {}

print(f'QID cache entries: {len(code_to_qid)}')

# Build clean QS - deduplicate by (qid, lat, lon)
seen_qs = set()
qs_lines = []
csv_rows = []

cc_map = {x['code']: x for x in cc}

for fix in cc:
    code = fix['code']
    lat = fix['lat']
    lon = fix['lon']
    qid = code_to_qid.get(code)
    
    if qid:
        qs_key = (qid, round(lat, 6), round(lon, 6))
        if qs_key not in seen_qs:
            seen_qs.add(qs_key)
            line = f"{qid}\tP625\t@{lat}/{lon}"
            qs_lines.append(line)
    
    csv_rows.append({
        'code': code,
        'qid': qid or '',
        'old_lat': fix.get('old_lat') or '',
        'old_lon': fix.get('old_lon') or '',
        'new_lat': lat,
        'new_lon': lon,
        'source': fix['source'],
        'distance_m': fix.get('distance_corrected_m') or '',
        'notes': fix.get('notes', '')
    })

# Save clean QS
with open('data/qs_coord_corrections.qs', 'w', encoding='utf-8') as f:
    f.write('\n'.join(qs_lines) + '\n')
print(f'QuickStatements: {len(qs_lines)} unique QID/coord pairs')

# Save CSV summary
with open('data/coord_corrections_summary.csv', 'w', encoding='utf-8', newline='') as f:
    w = csv.DictWriter(f, fieldnames=['code', 'qid', 'old_lat', 'old_lon', 'new_lat', 'new_lon', 'source', 'distance_m', 'notes'])
    w.writeheader()
    w.writerows(csv_rows)
print(f'CSV summary: {len(csv_rows)} rows')

# Also update coords_corrected.json if Trostenets was added
with open('data/coords_corrected.json', 'w', encoding='utf-8') as f:
    json.dump(cc, f, ensure_ascii=False, indent=2)
print(f'coords_corrected.json: {len(cc)} total entries')

print('\n=== BY SOURCE ===')
from collections import Counter
for k, v in Counter(x['source'] for x in cc).most_common():
    print(f'  {k}: {v}')

print(f'\nWith QID (actionable for Wikidata): {len(qs_lines)}')
print(f'Without QID (need to find QID first): {len(cc) - len(qs_lines)}')
