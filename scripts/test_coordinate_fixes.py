import json
import re

with open('data/belarus_border_simple.json', 'r', encoding='utf-8') as f:
    poly = json.load(f)

def point_in_poly(x, y, poly):
    n = len(poly)
    inside = False
    p1x, p1y = poly[0]
    for i in range(1, n + 1):
        p2x, p2y = poly[i % n]
        if y > min(p1y, p2y) and y <= max(p1y, p2y) and x <= max(p1x, p2x):
            if p1y != p2y:
                xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
            if p1x == p2x or x <= xinters:
                inside = not inside
        p1x, p1y = p2x, p2y
    return inside

with open('data/monuments.json', 'r', encoding='utf-8') as f:
    monuments = json.load(f)

fixed_count = 0
purged_count = 0
fixed_list = []
purged_list = []

def parse_dms(val):
    s = str(val).strip()
    # Check if 6 digits before dot or no dot e.g. 530932 or 523846.65
    m = re.match(r'^(\d{2})(\d{2})(\d{2}(?:\.\d+)?)$', s)
    if m:
        deg = float(m.group(1))
        mn = float(m.group(2))
        sec = float(m.group(3))
        if mn < 60 and sec < 60:
            return deg + mn / 60.0 + sec / 3600.0
    # Check if DDMM.mmm e.g. 5241.917
    m2 = re.match(r'^(\d{2})(\d{2}\.\d+)$', s)
    if m2:
        deg = float(m2.group(1))
        mn = float(m2.group(2))
        if mn < 60:
            return deg + mn / 60.0
    return None

for m in monuments:
    lat = m.get('lat')
    lon = m.get('lon')
    if not lat or not lon:
        continue

    # First check if inside
    if point_in_poly(lon, lat, poly):
        continue

    orig_lat, orig_lon = lat, lon
    new_lat, new_lon = None, None
    fix_reason = ''

    # 1. Check swapped
    if 23.0 <= lat <= 33.0 and 51.0 <= lon <= 57.0:
        cand_lat, cand_lon = lon, lat
        if point_in_poly(cand_lon, cand_lat, poly):
            new_lat, new_lon = cand_lat, cand_lon
            fix_reason = 'Swapped lat/lon'

    # 2. Check DMS
    if not new_lat and (lat > 90 or lon > 90):
        dms_lat = parse_dms(lat) if lat > 90 else lat
        dms_lon = parse_dms(lon) if lon > 90 else lon
        if dms_lat and dms_lon and point_in_poly(dms_lon, dms_lat, poly):
            new_lat, new_lon = dms_lat, dms_lon
            fix_reason = 'Parsed DMS without dots'
        elif lat > 500 and str(lat).startswith('563.'): # 563.232311 -> 53.232311
            cand_lat = float(str(lat).replace('563.', '53.'))
            if point_in_poly(lon, cand_lat, poly):
                new_lat, new_lon = cand_lat, lon
                fix_reason = 'Typo 563 -> 53'

    # 3. Check digit typos
    if not new_lat:
        # Pskov: 58.xxx -> 53.xxx
        if 58.0 <= lat <= 58.5 and 27.5 <= lon <= 30.0:
            cand_lat = lat - 5.0
            if point_in_poly(lon, cand_lat, poly):
                new_lat, new_lon = cand_lat, lon
                fix_reason = 'Pskov typo 58 -> 53'
        # Oryol: lon 37.xxx -> 31.xxx (Vetka)
        elif 36.5 <= lon <= 38.0 and 52.0 <= lat <= 54.0:
            cand_lon = lon - 6.0
            if point_in_poly(cand_lon, lat, poly):
                new_lat, new_lon = lat, cand_lon
                fix_reason = 'Oryol typo 37 -> 31'
        # Olevsk: lat 51.151102 -> 52.151102 (Zhitkovichi)
        elif lat < 51.25 and 'Жыткавіч' in (m.get('dst') or ''):
            cand_lat = lat + 1.0
            if point_in_poly(lon, cand_lat, poly):
                new_lat, new_lon = cand_lat, lon
                fix_reason = 'Olevsk typo 51 -> 52'

    if new_lat and new_lon:
        fixed_count += 1
        fixed_list.append((m['c'], m['id'], fix_reason, f"{orig_lat}, {orig_lon}", f"{new_lat:.6f}, {new_lon:.6f}"))
    else:
        purged_count += 1
        purged_list.append((m['c'], m['id'], f"{m.get('r')}, {m.get('dst')}, {m.get('loc')}", f"{orig_lat}, {orig_lon}"))

print(f"Total outside: {fixed_count + purged_count}")
print(f"Fixed: {fixed_count}")
print(f"Purged to null (no coords): {purged_count}")
print("\n--- FIXED SAMPLE ---")
for x in fixed_list[:15]:
    print(x)
print("\n--- PURGED SAMPLE ---")
for x in purged_list[:15]:
    print(x)
