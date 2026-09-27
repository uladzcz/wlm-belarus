import json, sys
from collections import Counter
sys.stdout.reconfigure(encoding='utf-8')

cc = json.load(open('data/coords_corrected.json', encoding='utf-8'))
orig = json.load(open('data/monuments.json', encoding='utf-8'))
corr = json.load(open('data/monuments_corrected.json', encoding='utf-8'))

# Count by source
sources = Counter(x['source'] for x in cc)
print('Corrections by source:')
for k, v in sources.most_common():
    print(f'  {k}: {v}')

print(f'\nTotal corrections: {len(cc)}')

# Coverage before/after
orig_with = sum(1 for m in orig if m.get('lat') is not None)
corr_with = sum(1 for m in corr if m.get('lat') is not None)
print(f'\nCoord coverage BEFORE: {orig_with}/{len(orig)} ({orig_with*100/len(orig):.1f}%)')
print(f'Coord coverage AFTER:  {corr_with}/{len(corr)} ({corr_with*100/len(corr):.1f}%)')
print(f'New coords added:      {corr_with - orig_with}')

# Check key test cases
cc_map = {x['code']: x for x in cc}
for code in ['413Г000659', '113Д000639', '413В000189', '711Д000283']:
    fix = cc_map.get(code)
    if fix:
        print(f"\n{code}: {fix['source']} | {fix['lat']},{fix['lon']} | dist={fix['distance_corrected_m']}m")
    else:
        print(f"\n{code}: NOT in corrections")

# Check QS file
import os
if os.path.exists('data/qs_coord_corrections.qs'):
    with open('data/qs_coord_corrections.qs', encoding='utf-8') as f:
        lines = f.readlines()
    print(f'\nQuickStatements file: {len(lines)} lines')
    print(lines[:3])
else:
    print('\nNo QS file found yet.')

if os.path.exists('data/coord_corrections_summary.csv'):
    with open('data/coord_corrections_summary.csv', encoding='utf-8') as f:
        rows = f.readlines()
    print(f'\nCSV summary: {len(rows)} rows')
