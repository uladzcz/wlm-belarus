import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('data/monuments_outside_border.json', 'r', encoding='utf-8') as f:
    outside = json.load(f)

print(f'Total outside: {len(outside)}')
print('-' * 120)

categories = {
    'swapped_lat_lon': [], # lat ~25-33, lon ~51-56
    'dms_or_no_dot': [],   # lat > 100 or lon > 100
    'lat_equals_lon': [],  # lat == lon
    'typo_digit': [],      # e.g. 58 instead of 53, or 37 instead of 31, or 54.51 / 54.51
    'border_crossing': []  # slightly across border (e.g. Ukraine, Lithuania, Russia within 10-30km)
}

for i, m in enumerate(outside):
    c = m.get('c', '')
    t = (m.get('t') or '')[:30]
    r = m.get('r') or ''
    dst = m.get('dst') or ''
    loc = m.get('loc') or ''
    lat = m.get('lat')
    lon = m.get('lon')

    err_type = 'unknown'
    if lat > 100 or lon > 100:
        err_type = 'dms_or_no_dot'
    elif 23 <= lat <= 33 and 51 <= lon <= 56:
        err_type = 'swapped_lat_lon'
    elif abs(lat - lon) < 0.0001:
        err_type = 'lat_equals_lon'
    elif lat > 57 or lon > 35 or lon < 22:
        err_type = 'typo_digit'
    else:
        err_type = 'border_crossing'

    categories[err_type].append(m)
    print(f"{i+1:2d}. [{err_type:16}] {c:12} | {t:30} | {r}, {dst}, {loc} | {lat}, {lon}")

print('=' * 120)
for k, v in categories.items():
    print(f"Error category '{k}': {len(v)} items")
