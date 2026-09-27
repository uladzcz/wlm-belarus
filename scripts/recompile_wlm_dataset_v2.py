import json
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

SRC_EXHIBITS = '../heritage-wrapper/data/exhibits_indexed.json'
SRC_COORDS = '../heritage-wrapper/data/coords.json'
SRC_PHOTOS = '../heritage-wrapper/data/wlm_existing_photos.json'
SRC_DISTRICTS = '../heritage-wrapper/data/districts_qids.json'
SRC_COMMONS_CATS = '../heritage-wrapper/data/wlm_commons_categories.json'
SRC_WD_COORDS = '../heritage-wrapper/data/belarus_all_coords.json'
SRC_BORDER = 'data/belarus_border_simple.json'

OUT_PATH = 'data/monuments.json'
OUT_QS_BAD_COORDS = 'data/qs_remove_bad_coords.qs'

print("Loading data files...")
with open(SRC_EXHIBITS, 'r', encoding='utf-8') as f:
    exhibits = json.load(f)

with open(SRC_COORDS, 'r', encoding='utf-8') as f:
    coords = json.load(f)

with open(SRC_DISTRICTS, 'r', encoding='utf-8') as f:
    districts_map = json.load(f)

with open(SRC_BORDER, 'r', encoding='utf-8') as f:
    border_poly = json.load(f)

commons_cats = {}
if os.path.exists(SRC_COMMONS_CATS):
    with open(SRC_COMMONS_CATS, 'r', encoding='utf-8') as f:
        commons_cats = json.load(f)

photos_map = {}
if os.path.exists(SRC_PHOTOS):
    with open(SRC_PHOTOS, 'r', encoding='utf-8') as f:
        pdata = json.load(f)
        for item in pdata:
            c = item.get('code')
            if c:
                photos_map[c] = {
                    'image': item.get('image'),
                    'qid': item.get('qid')
                }

# Wikidata QID -> (lat, lon)
wd_coords_map = {}
if os.path.exists(SRC_WD_COORDS):
    with open(SRC_WD_COORDS, 'r', encoding='utf-8') as f:
        wd_raw = json.load(f)
        for entry in wd_raw:
            qid = entry.get('item', {}).get('value', '').split('/')[-1]
            pt_str = entry.get('coords', {}).get('value', '')
            if 'Point(' in pt_str:
                parts = pt_str.replace('Point(', '').replace(')', '').strip().split()
                if len(parts) == 2:
                    try:
                        flon = float(parts[0])
                        flat = float(parts[1])
                        wd_coords_map[qid] = (flat, flon)
                    except ValueError:
                        pass

print(f"Loaded {len(exhibits)} exhibits, {len(coords)} heritage coords, {len(wd_coords_map)} Wikidata coords.")

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

def parse_dms(val):
    s = str(val).strip()
    m = re.match(r'^(\d{2})(\d{2})(\d{2}(?:\.\d+)?)$', s)
    if m:
        deg = float(m.group(1))
        mn = float(m.group(2))
        sec = float(m.group(3))
        if mn < 60 and sec < 60:
            return deg + mn / 60.0 + sec / 3600.0
    m2 = re.match(r'^(\d{2})(\d{2}\.\d+)$', s)
    if m2:
        deg = float(m2.group(1))
        mn = float(m2.group(2))
        if mn < 60:
            return deg + mn / 60.0
    return None

monuments = []
stats = {
    'total': len(exhibits),
    'with_coords': 0,
    'from_wikidata': 0,
    'fixed_swapped': 0,
    'fixed_dms': 0,
    'fixed_typo': 0,
    'purged_outside': 0,
    'marat_kazey_purged': 0,
    'with_photos': 0,
    'districts_mapped': 0
}

bad_coords_to_remove_from_wd = []

for e in exhibits:
    slug = e.get('id')
    code = e.get('code') or ''
    title = e.get('title') or e.get('name_be') or 'Помнік'
    # Extract clean category: '0', '1', '2', '3', 'А', 'Б'
    raw_cat = str(e.get('category') or '').strip().lower()
    if 'сусветны' in raw_cat:
        cat = '0'
    elif 'міжнароднага' in raw_cat:
        cat = '1'
    elif 'нацыянальнага' in raw_cat:
        cat = '2'
    elif 'рэгіянальнага' in raw_cat:
        cat = '3'
    elif 'аўтэнтычныя' in raw_cat or ' - а' in raw_cat:
        cat = 'А'
    elif 'адноўленыя' in raw_cat or ' - б' in raw_cat:
        cat = 'Б'
    else:
        # Fallback check on official code 3rd character (e.g. 213Д000528 -> '3')
        if len(code) >= 3 and code[2] in '0123':
            cat = code[2]
        else:
            cat = ''

    # Extract heritage form: 'immovable' (WLM eligible), 'movable', 'intangible'
    raw_form = str(e.get('form') or 'Immovable').strip()
    if raw_form == 'Intangible' or 'нематэрыяльн' in raw_form.lower():
        form = 'intangible'
    elif raw_form == 'Movable' or (raw_form.lower().startswith('рухом') and not 'нерухом' in raw_form.lower()):
        form = 'movable'
    else:
        form = 'immovable'

    tp = e.get('type') or 'Помнік гісторыі і культуры'
    dating = e.get('dating') or ''
    city = e.get('city') or ''
    addr = e.get('address') or ''

    # 1. District and Region resolution
    raw_district = e.get('district') or ''
    district_be = ''
    region_be = e.get('region') or ''

    if raw_district and raw_district in districts_map:
        dq_entry = districts_map[raw_district]
        district_be = dq_entry.get('name_be', '')
        if not region_be or region_be in ['Minsk', 'г. Мінск', 'г.Мінск']:
            region_be = dq_entry.get('region_name', region_be)
        stats['districts_mapped'] += 1
    elif raw_district and ('раён' in raw_district.lower() or raw_district.startswith('г.')):
        district_be = raw_district
    else:
        district_be = ''

    if region_be in ['Minsk', 'г.Мінск']:
        region_be = 'г. Мінск'
    elif region_be == 'MinskRegion':
        region_be = 'Мінская вобласць'
    elif region_be == 'BrestRegion':
        region_be = 'Брэсцкая вобласць'
    elif region_be == 'VitebskRegion':
        region_be = 'Віцебская вобласць'
    elif region_be == 'GrodnoRegion':
        region_be = 'Гродзенская вобласць'
    elif region_be == 'GomelRegion':
        region_be = 'Гомельская вобласць'
    elif region_be == 'MogilevRegion':
        region_be = 'Магілёўская вобласць'

    # 2. Photos & Wikidata resolution
    photo_info = photos_map.get(code)
    has_photo = False
    image_url = None
    qid = None
    if photo_info:
        has_photo = True
        image_url = photo_info.get('image')
        qid = photo_info.get('qid')
        stats['with_photos'] += 1

    # 3. Coordinates Resolution with Multi-source Fallback & Repair
    lat = None
    lon = None

    # Priority A: Check if Wikidata has valid coordinates for this QID
    if qid and qid in wd_coords_map:
        wlat, wlon = wd_coords_map[qid]
        # Verify Wikidata coords are inside Belarus
        if point_in_poly(wlon, wlat, border_poly):
            lat = round(wlat, 6)
            lon = round(wlon, 6)
            stats['from_wikidata'] += 1

    # Priority B: If no Wikidata coords, check heritage.gov.by
    if lat is None:
        c = coords.get(slug, {})
        hlat = c.get('lat') or e.get('lat')
        hlon = c.get('lon') or e.get('lon')

        if hlat and hlon:
            try:
                flat = float(hlat)
                flon = float(hlon)

                # Check dummy Marat Kazey park
                if abs(flat - 53.90797) < 0.0005 and abs(flon - 27.563541) < 0.0005:
                    stats['marat_kazey_purged'] += 1
                elif point_in_poly(flon, flat, border_poly):
                    lat = round(flat, 6)
                    lon = round(flon, 6)
                else:
                    # Point is OUTSIDE Belarus -> Attempt deterministic repairs
                    # 1. Swapped lat/lon (e.g. Barysaw items, Bezdzezh, Gomel)
                    if 23.0 <= flat <= 33.0 and 51.0 <= flon <= 57.0:
                        if point_in_poly(flat, flon, border_poly):
                            lat = round(flon, 6)
                            lon = round(flat, 6)
                            stats['fixed_swapped'] += 1

                    # 2. DMS without dots (e.g. Vawkavysk 530932.0, 242818.0)
                    if lat is None and (flat > 90 or flon > 90):
                        dms_lat = parse_dms(flat) if flat > 90 else flat
                        dms_lon = parse_dms(flon) if flon > 90 else flon
                        if dms_lat and dms_lon and point_in_poly(dms_lon, dms_lat, border_poly):
                            lat = round(dms_lat, 6)
                            lon = round(dms_lon, 6)
                            stats['fixed_dms'] += 1
                        elif flat > 500 and str(flat).startswith('563.'):
                            cand_lat = float(str(flat).replace('563.', '53.'))
                            if point_in_poly(flon, cand_lat, border_poly):
                                lat = round(cand_lat, 6)
                                lon = round(flon, 6)
                                stats['fixed_typo'] += 1

                    # 3. Single-digit typos
                    if lat is None:
                        # Pskov: 58.xxx -> 53.xxx (Osipovichi)
                        if 58.0 <= flat <= 58.5 and 27.5 <= flon <= 30.0:
                            cand_lat = flat - 5.0
                            if point_in_poly(flon, cand_lat, border_poly):
                                lat = round(cand_lat, 6)
                                lon = round(flon, 6)
                                stats['fixed_typo'] += 1
                        # Oryol: lon 37.xxx -> 31.xxx (Vetka)
                        elif 36.5 <= flon <= 38.0 and 52.0 <= flat <= 54.0:
                            cand_lon = flon - 6.0
                            if point_in_poly(cand_lon, flat, border_poly):
                                lat = round(flat, 6)
                                lon = round(cand_lon, 6)
                                stats['fixed_typo'] += 1
                        # Olevsk: lat 51.151102 -> 52.151102 (Zhitkovichi)
                        elif flat < 51.25 and 'Жыткавіч' in district_be:
                            cand_lat = flat + 1.0
                            if point_in_poly(flon, cand_lat, border_poly):
                                lat = round(cand_lat, 6)
                                lon = round(flon, 6)
                                stats['fixed_typo'] += 1

                    # If still outside Belarus or bogus, PURGE!
                    if lat is None:
                        stats['purged_outside'] += 1
                        if qid:
                            bad_coords_to_remove_from_wd.append((qid, code, flat, flon))
            except ValueError:
                pass

    if lat and lon:
        stats['with_coords'] += 1

    # 4. Commons category resolution
    cat_commons = None
    if code in commons_cats:
        cat_commons = commons_cats[code]
    elif code:
        cat_commons = code

    monument = {
        'id': slug,
        'c': code,
        't': title,
        'cat': cat,
        'tp': tp,
        'd': dating,
        'r': region_be,
        'dst': district_be,
        'loc': city,
        'a': addr,
        'p': 1 if has_photo else 0,
        'f': form,
    }
    if lat and lon:
        monument['lat'] = lat
        monument['lon'] = lon
    if image_url:
        if image_url.startswith('http://'):
            image_url = 'https://' + image_url[7:]
        monument['img'] = image_url
    if qid:
        monument['qid'] = qid
    if cat_commons:
        monument['ccat'] = cat_commons

    monuments.append(monument)

# Sort: items with coordinates first, then alphabetical by title
monuments.sort(key=lambda m: (0 if 'lat' in m else 1, m['t']))

with open(OUT_PATH, 'w', encoding='utf-8') as f:
    json.dump(monuments, f, ensure_ascii=False, separators=(',', ':'))

# QuickStatements for bad coords
with open(OUT_QS_BAD_COORDS, 'w', encoding='utf-8') as f:
    f.write("/* QuickStatements: Remove bogus cross-border coordinates from Wikidata */\n")
    for qid, code, b_lat, b_lon in bad_coords_to_remove_from_wd:
        f.write(f"-{qid}\tP625\t@{b_lat}/{b_lon}\n")

file_size_mb = os.path.getsize(OUT_PATH) / (1024 * 1024)
print(f"\nDataset compiled successfully to {OUT_PATH}!")
print(f"File size: {file_size_mb:.2f} MB")
print(f"Total monuments: {stats['total']}")
print(f"With coordinates: {stats['with_coords']}")
print(f"Without coordinates: {stats['total'] - stats['with_coords']}")
print(f"Coordinates loaded from Wikidata (P625): {stats['from_wikidata']}")
print(f"Swapped coordinates repaired: {stats['fixed_swapped']}")
print(f"DMS coordinates repaired: {stats['fixed_dms']}")
print(f"Digit typos repaired: {stats['fixed_typo']}")
print(f"Bogus cross-border coordinates purged to null: {stats['purged_outside']}")
print(f"Marat Kazey fake coordinates purged to null: {stats['marat_kazey_purged']}")
print(f"With photos: {stats['with_photos']}")
print(f"Districts mapped to clean Belarusian: {stats['districts_mapped']}")
print(f"QuickStatements saved to {OUT_QS_BAD_COORDS} ({len(bad_coords_to_remove_from_wd)} items)")
