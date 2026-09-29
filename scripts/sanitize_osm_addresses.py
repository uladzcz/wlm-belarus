import json
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

corr = json.load(open('data/coords_corrected.json', encoding='utf-8'))
osm_matches = json.load(open('data/matched_osm_addresses.json', encoding='utf-8'))['matches']

applied_osm = [c for c in corr if c.get('source') == 'osm_address']
print(f"Total applied osm_address entries: {len(applied_osm)}")

# We will classify every entry
to_purge = {}

for c in applied_osm:
    code = c['code']
    m = osm_matches.get(code)
    if not m:
        to_purge[code] = "No match record in matched_osm_addresses"
        continue
    
    title = m.get('title', '')
    raw_addr = m.get('raw_address', '')
    p_st = m.get('parsed_street', '').lower().strip()
    p_house = m.get('parsed_house', '').lower().strip()
    disp = m.get('display_name', '')
    disp_l = disp.lower()
    dist = c.get('distance_corrected_m', 0)
    osm_class = m.get('osm_class', '')
    osm_detail = m.get('osm_type_detail', '')
    settlement = m.get('settlement', '').lower().replace('г.', '').replace('в.', '').replace('г.п.', '').replace('аг.', '').strip()
    
    # 1. Town/settlement mismatch
    if settlement and settlement not in disp_l:
        to_purge[code] = f"Town mismatch: expected '{settlement}' but got OSM '{disp}'"
        continue
        
    # 2. Lane vs street mismatch (e.g. 2-і завулак Дзекабрыстаў vs вул. Дзекабрыстаў, зав. Ціміразева vs вул. Ціміразева)
    if ('завулак' in disp_l or 'пер.' in disp_l) and not ('завулак' in raw_addr.lower() or 'пер.' in raw_addr.lower()):
        to_purge[code] = f"Lane mismatch: expected street but matched lane '{disp}'"
        continue
        
    # 3. Grave/cemetery/burial/park placed on an ordinary house or shop
    is_cemetery_or_grave = any(w in (title + raw_addr).lower() for w in ['магіл', 'могілк', 'могільнік', 'пахаван'])
    if is_cemetery_or_grave and osm_class == 'building' and osm_detail in ['yes', 'apartments', 'house']:
        to_purge[code] = f"Grave/cemetery placed on residential building: '{disp}'"
        continue

    # 4. Church/Cathedral/Belfry placed on a hardware store or shop or ordinary house
    is_church = any(w in title.lower() for w in ['сабор', 'царква', 'касцёл', 'званіца', 'манастыр', 'сінагога'])
    if is_church and osm_detail in ['hardware', 'shop', 'commercial', 'supermarket']:
        to_purge[code] = f"Church/sacral placed on commercial/hardware: '{disp}'"
        continue

    # 5. Distance discrepancy > 1500m (in urban contexts, a building address move > 1.5km is almost always a wrong match, unless it's a known multi-part complex)
    if dist > 1500:
        # Check if the building in OSM has a name that explicitly matches the monument
        name_in_disp = any(w in disp_l for w in ['тэатр', 'тэатра', 'музей', 'ратуша', 'касцёл', 'царква'])
        if not name_in_disp:
            to_purge[code] = f"Large distance discrepancy ({dist:.0f}m) without POI name match: '{disp}'"
            continue

print(f"\nTotal matches flagged to PURGE: {len(to_purge)}")
for code, reason in to_purge.items():
    print(f"  {code}: {reason}")
