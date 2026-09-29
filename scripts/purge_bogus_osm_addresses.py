import json
import csv
import sys

sys.stdout.reconfigure(encoding='utf-8')

# The 20 bogus codes
BOGUS_CODES = {
    '112Е000002_74', '112Е000383_27', '412Г000014_2', '613Г000670', '613Г000671', 
    '113Д000023_1', '113Д000023_3', '113Д000023_2', '113Д000023_6', '113Д000023_8', 
    '113Д000023_5', '113Д000023_7', '113Д000023_4', '411Г000319_3', '712Г000010_2', 
    '712Г000010_3', '712Г000010_1', '412Г000033_1', '413Г000653', '112Г000151_1'
}

print(f"Purging {len(BOGUS_CODES)} bogus OSM address matches...")

# 1. Update coords_corrected.json
corr = json.load(open('data/coords_corrected.json', encoding='utf-8'))
corr_before = len(corr)
old_coords_map = {}
for c in corr:
    if c['code'] in BOGUS_CODES:
        old_coords_map[c['code']] = (c.get('old_lat'), c.get('old_lon'))

clean_corr = [c for c in corr if c['code'] not in BOGUS_CODES]
with open('data/coords_corrected.json', 'w', encoding='utf-8') as f:
    json.dump(clean_corr, f, ensure_ascii=False, indent=2)
print(f"coords_corrected.json: {corr_before} -> {len(clean_corr)} entries")

# 2. Revert in monuments.json and monuments_corrected.json
mon = json.load(open('data/monuments.json', encoding='utf-8'))
for m in mon:
    code = m.get('c')
    if code in BOGUS_CODES:
        old_lat, old_lon = old_coords_map.get(code, (None, None))
        m['lat'] = old_lat
        m['lon'] = old_lon

with open('data/monuments.json', 'w', encoding='utf-8') as f:
    json.dump(mon, f, ensure_ascii=False, indent=2)

mon_corr = json.load(open('data/monuments_corrected.json', encoding='utf-8'))
for m in mon_corr:
    code = m.get('c')
    if code in BOGUS_CODES:
        old_lat, old_lon = old_coords_map.get(code, (None, None))
        m['lat'] = old_lat
        m['lon'] = old_lon

with open('data/monuments_corrected.json', 'w', encoding='utf-8') as f:
    json.dump(mon_corr, f, ensure_ascii=False, indent=2)

print("Reverted monuments.json and monuments_corrected.json")

# 3. Regenerate coord_corrections_summary.csv and qs_coord_corrections.qs
# Load wikidata cache
wd_cache = json.load(open('data/wikidata_p632_cache.json', encoding='utf-8'))

summary_rows = []
qs_lines = []

for c in clean_corr:
    code = c['code']
    qid = wd_cache.get(code, '')
    new_lat = c['lat']
    new_lon = c['lon']
    old_lat = c.get('old_lat', '')
    old_lon = c.get('old_lon', '')
    source = c.get('source', '')
    dist = c.get('distance_corrected_m', '')
    notes = c.get('notes', '')
    
    summary_rows.append({
        'code': code,
        'qid': qid,
        'old_lat': old_lat,
        'old_lon': old_lon,
        'new_lat': new_lat,
        'new_lon': new_lon,
        'source': source,
        'distance_m': dist,
        'notes': notes
    })
    
    if qid:
        if old_lat and old_lon:
            qs_lines.append(f"- {qid}\tP625\t@{old_lat}/{old_lon}")
        qs_lines.append(f"{qid}\tP625\t@{new_lat:.6f}/{new_lon:.6f}")

with open('data/coord_corrections_summary.csv', 'w', encoding='utf-8', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=['code', 'qid', 'old_lat', 'old_lon', 'new_lat', 'new_lon', 'source', 'distance_m', 'notes'])
    writer.writeheader()
    writer.writerows(summary_rows)

with open('data/qs_coord_corrections.qs', 'w', encoding='utf-8') as f:
    f.write('\n'.join(qs_lines) + '\n')

print(f"Regenerated summary CSV ({len(summary_rows)} rows) and qs_coord_corrections.qs ({len(qs_lines)} lines)")

# 4. Verify Baranovichi entries are gone from QS
for line in qs_lines:
    if '53.114379' in line or '26.01016' in line:
        print("ERROR: 53.114379 still in QS!")
        break
else:
    print("VERIFIED: 53.114379 is completely absent from qs_coord_corrections.qs!")
