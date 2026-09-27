import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('data/monuments_outside_border.json', 'r', encoding='utf-8') as f:
    outside = json.load(f)

print("=== BORDER CROSSING CANDIDATES ===")
for m in outside:
    lat = m.get('lat')
    lon = m.get('lon')
    if (lat <= 57 and lon <= 35 and lon >= 22 and abs(lat-lon) > 0.01 
        and not (23 <= lat <= 33 and 51 <= lon <= 56) and lat < 100 and lon < 100):
        c = m.get('c')
        t = m.get('t', '')[:35]
        dst = m.get('dst', '')
        loc = m.get('loc', '')
        print(f"{c:12} | {t:35} | {dst:20} | {loc:20} | {lat:.6f}, {lon:.6f}")
