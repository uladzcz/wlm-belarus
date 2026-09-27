import os
import re
import json
import math
import glob
import pymupdf
import sys

sys.stdout.reconfigure(encoding='utf-8')

def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371000.0  # Earth radius in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2.0)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0)**2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c

# Transliteration / character normalization for heritage codes
CYR_LAT_MAP = {
    'A': 'А', 'B': 'В', 'E': 'Е', 'K': 'К', 'M': 'М', 'H': 'Н', 'O': 'О', 'P': 'Р', 'C': 'С', 'T': 'Т',
    'а': 'А', 'в': 'В', 'е': 'Е', 'к': 'К', 'м': 'М', 'н': 'Н', 'о': 'О', 'р': 'Р', 'с': 'С', 'т': 'Т',
    'г': 'Г', 'д': 'Д', 'ж': 'Ж', 'з': 'З', 'і': 'І', 'й': 'Й', 'л': 'Л', 'п': 'П', 'у': 'У', 'ф': 'Ф',
    'х': 'Х', 'ц': 'Ц', 'ч': 'Ч', 'ш': 'Ш', 'ы': 'Ы', 'ь': 'Ь', 'э': 'Э', 'ю': 'Ю', 'я': 'Я'
}

def normalize_code(code_str):
    if not code_str:
        return ""
    code_str = code_str.strip().upper()
    if len(code_str) >= 4:
        c4 = code_str[3]
        if c4 in CYR_LAT_MAP:
            code_str = code_str[:3] + CYR_LAT_MAP[c4] + code_str[4:]
    return code_str

def normalize_text(s):
    if not s:
        return ""
    s = s.lower()
    s = re.sub(r'[\s\n\r\t]+', ' ', s)
    s = re.sub(r'[«»\"\'\(\),.:;\-–—]', ' ', s)
    return ' '.join(s.split())

def parse_points_from_page(text):
    """
    Extract (pt_num, lat, lon) from page text.
    Handles multiple table formats:
    - № кропкі / каардынаты
    - 1  53.123456, 26.123456
    - 1 \n 53.123456 \n 26.123456
    - Comma as decimal separator: 53,123456, 26,123456
    """
    points = {}
    
    # 1. Regex for: point_num followed by lat, lon on same line or separated by comma/space
    pat1 = re.findall(r'(?:\b|^)(\d{1,4})\s+([56]\d[.,]\d{4,8})[,\s]+([23]\d[.,]\d{4,8})', text)
    for pt, lat_s, lon_s in pat1:
        try:
            pt_num = int(pt)
            lat = float(lat_s.replace(',', '.'))
            lon = float(lon_s.replace(',', '.'))
            if 51.0 <= lat <= 56.6 and 23.0 <= lon <= 33.0:
                if pt_num not in points:
                    points[pt_num] = (lat, lon)
        except:
            pass

    # 2. Check line by line or token stream
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    for i in range(len(lines)):
        line = lines[i]
        if re.match(r'^\d{1,4}$', line):
            pt_num = int(line)
            if i + 1 < len(lines):
                next_l = lines[i+1]
                m_pair = re.search(r'([56]\d[.,]\d{4,8})[,\s]+([23]\d[.,]\d{4,8})', next_l)
                if m_pair:
                    lat = float(m_pair.group(1).replace(',', '.'))
                    lon = float(m_pair.group(2).replace(',', '.'))
                    if 51.0 <= lat <= 56.6 and 23.0 <= lon <= 33.0:
                        if pt_num not in points:
                            points[pt_num] = (lat, lon)
            if i + 2 < len(lines) and pt_num not in points:
                l1 = lines[i+1]
                l2 = lines[i+2]
                m_lat = re.search(r'^([56]\d[.,]\d{4,8})$', l1)
                m_lon = re.search(r'^([23]\d[.,]\d{4,8})$', l2)
                if m_lat and m_lon:
                    lat = float(m_lat.group(1).replace(',', '.'))
                    lon = float(m_lon.group(1).replace(',', '.'))
                    if 51.0 <= lat <= 56.6 and 23.0 <= lon <= 33.0:
                        points[pt_num] = (lat, lon)
                        
    # 3. Fallback: if no point numbers associated, extract all lat/lon pairs
    if not points:
        all_pairs = re.findall(r'([56]\d[.,]\d{4,8})[,\s]+([23]\d[.,]\d{4,8})', text)
        idx = 1
        for lat_s, lon_s in all_pairs:
            lat = float(lat_s.replace(',', '.'))
            lon = float(lon_s.replace(',', '.'))
            if 51.0 <= lat <= 56.6 and 23.0 <= lon <= 33.0:
                points[idx] = (lat, lon)
                idx += 1

    return points

def isolate_territory_chapter(full_text):
    """
    Locates the section strictly defining 'Тэрыторыя гісторыка-культурнай каштоўнасці'.
    Stops before any protective / buffer zones ('Ахоўная зона', 'Зона рэгулявання забудовы',
    'Зона аховы ландшафту', 'Зона аховы культурнага пласта', 'Дадатак').
    """
    m = re.search(
        r'(ГЛАВА\s+\d+[.\s]+(?:ТЭРЫТОРЫ|МЕЖЫ\s+ТЭРЫТОРЫ)[^\n]*)(.*?)(?=(?:ГЛАВА\s+\d+[.\s]+(?:АХОЎНАЯ\s+ЗОНА|ЗОНА\s+РЭГУЛЯВАННЯ|ЗОНА\s+АХОВЫ\s+ЛАНДШАФТУ|ЗОНА\s+АХОВЫ\s+КУЛЬТУРНАГА\s+ПЛАСТА)|ДАДАТАК|\Z))',
        full_text, re.DOTALL | re.IGNORECASE
    )
    if m:
        return m.group(0), "territory"

    # Fallback: Decrees where Chapter 2 is 'АХОЎНАЯ ЗОНА' because no separate territory was defined
    m2 = re.search(
        r'(ГЛАВА\s+2[.\s]+АХОЎНАЯ\s+ЗОНА[^\n]*)(.*?)(?=(?:ГЛАВА\s+\d+[.\s]+(?:ЗОНА\s+РЭГУЛЯВАННЯ|ЗОНА\s+АХОВЫ\s+ЛАНДШАФТУ|ЗОНА\s+АХОВЫ\s+КУЛЬТУРНАГА\s+ПЛАСТА)|ДАДАТАК|\Z))',
        full_text, re.DOTALL | re.IGNORECASE
    )
    if m2:
        return m2.group(0), "protection_zone"

    return full_text, "fallback"

def parse_points_from_clause(clause_text, available_points=None):
    """
    Extracts point numbers strictly within a boundary definition paragraph.
    Handles:
    - 'ад кропкі 1', 'да кропкі 10'
    - 'праз кропкі 15–16–17–18–19–20'
    - 'пункты 1–36'
    - 'кропкі 71, 72, 73'
    - chains like 1-2-3-4
    Avoids house numbers or street numbers like 'вул. Горкага, 7, 9, 11'.
    """
    pts = set()

    for m in re.finditer(r'(?:ад|да|у|з|каля)\s+(?:паваротнай\s+)?кропк[іаеу]\s+(\d{1,4})', clause_text, re.IGNORECASE):
        pts.add(int(m.group(1)))

    for m in re.finditer(r'(?:праз\s+)?(?:паваротныя\s+)?(?:кропкі|кропак|пункты|пунктаў)\s+([0-9\s,\-–—іда]+)', clause_text, re.IGNORECASE):
        chunk = m.group(1)
        for r in re.finditer(r'(\d{1,4})\s*[-–—]\s*(\d{1,4})', chunk):
            s, e = int(r.group(1)), int(r.group(2))
            if s <= e and e - s <= 200:
                for k in range(s, e + 1):
                    pts.add(k)
        for n in re.findall(r'\b\d{1,4}\b', chunk):
            pts.add(int(n))

    for m in re.finditer(r'\b(\d{1,4})(?:\s*[-–—]\s*\d{1,4}){2,}\b', clause_text):
        for n in re.findall(r'\b\d{1,4}\b', m.group(0)):
            pts.add(int(n))

    if available_points:
        pts = {p for p in pts if p in available_points}

    return sorted(list(pts))

def parse_boundary_clauses(ch_text, available_points=None):
    """
    Splits territory chapter into distinct boundary clauses.
    Returns list of dicts with:
    - para_num
    - quotes (titles mentioned in «...»)
    - points (list of int point indices)
    - inline_coords (list of (lat, lon) pairs)
    - text, snippet
    """
    paras = re.split(r'\n(?=\s*\d+\.\s+)', ch_text)
    clauses = []
    for p in paras:
        p_str = p.strip()
        if not p_str:
            continue
        if not re.search(r'\b(?:мяж|меж|тэрыторы|пункт|кропк)', p_str, re.IGNORECASE):
            continue
        # Skip pure prohibition paragraphs ('забараняецца')
        if re.search(r'\bзабараняецца\b', p_str, re.IGNORECASE) and not re.search(r'\bз’яўляецца\b', p_str, re.IGNORECASE):
            continue

        quotes = [q.replace('\n', ' ').strip() for q in re.findall(r'«([^»]+)»', p_str)
                  if len(q.strip()) > 2 and not q.strip().isdigit()]

        pts = parse_points_from_clause(p_str, available_points)

        inline_coords = []
        if not pts:
            coord_matches = re.findall(r'([56]\d[.,]\d{4,8})[,\s]+([23]\d[.,]\d{4,8})', p_str)
            for lat_s, lon_s in coord_matches:
                lat = float(lat_s.replace(',', '.'))
                lon = float(lon_s.replace(',', '.'))
                if 51.0 <= lat <= 56.6 and 23.0 <= lon <= 33.0:
                    inline_coords.append((lat, lon))

        if pts or inline_coords:
            num_m = re.match(r'^\s*(\d+)\.', p_str)
            para_num = int(num_m.group(1)) if num_m else None
            clauses.append({
                'para_num': para_num,
                'quotes': quotes,
                'points': pts,
                'inline_coords': inline_coords,
                'text': p_str,
                'snippet': ' '.join(p_str.split()[:25])
            })
    return clauses

def match_monument_to_clause(code, mon_obj, clauses):
    """
    Scores and matches a monument against candidate clauses.
    Returns (best_clause, score).
    """
    mon_title = mon_obj.get('t', '')
    t_norm = normalize_text(mon_title)
    t_words = set(t_norm.split())

    best_clause = None
    best_score = 0.0

    m_num = re.search(r'[-–—\s](\d+)\b', mon_title)
    target_id_num = m_num.group(1) if m_num else None

    for cl in clauses:
        score = 0.0
        cl_quotes_norm = [normalize_text(q) for q in cl['quotes']]
        cl_text_norm = normalize_text(cl['text'])

        for q in cl_quotes_norm:
            if not q:
                continue
            if q == t_norm:
                score = max(score, 100.0)
            elif q in t_norm or t_norm in q:
                score = max(score, 80.0)
            else:
                q_words = set(q.split())
                overlap = len(q_words & t_words)
                if overlap >= 2:
                    jaccard = overlap / len(q_words | t_words)
                    score = max(score, 40.0 + jaccard * 30.0)

        if score == 0.0:
            cl_words = set(cl_text_norm.split())
            overlap = len(cl_words & t_words)
            if overlap >= 2:
                jaccard = overlap / len(cl_words | t_words)
                score = max(score, 20.0 + jaccard * 20.0)

        if target_id_num:
            cl_has_num = bool(re.search(rf'[-–—\s]{target_id_num}\b', cl['text']))
            if cl_has_num:
                score += 30.0
            else:
                cl_other_nums = re.findall(r'[-–—\s](\d+)\b', ' '.join(cl['quotes']))
                if cl_other_nums and target_id_num not in cl_other_nums:
                    score -= 50.0

        if score > best_score:
            best_score = score
            best_clause = cl

    return best_clause, best_score

def main():
    print("Loading base monuments dataset from data/monuments.json...")
    with open('data/monuments.json', encoding='utf-8') as f:
        monuments_list = json.load(f)
    print(f"Loaded {len(monuments_list)} monuments.")

    monuments_by_code = {}
    monuments_by_prefix_suffix = {}
    coord_counts = {}
    for m in monuments_list:
        c = normalize_code(m.get('c', ''))
        if c:
            monuments_by_code[c] = m
            if len(c) == 10:
                key = (c[0], c[3], c[4:])
                monuments_by_prefix_suffix[key] = m
        if m.get('lat') and m.get('lon'):
            key = (round(m['lat'], 4), round(m['lon'], 4))
            coord_counts[key] = coord_counts.get(key, 0) + 1

    with open('data/pravo_decrees_list.json', encoding='utf-8') as f:
        decrees_list = json.load(f)
    print(f"Loaded {len(decrees_list)} decrees to parse.")

    processed_decrees = {}
    matched_results = []
    
    total_decrees_with_coords = 0
    total_new_coords_found = 0
    total_suspicious_flagged = 0
    total_verified_coords = 0
    total_flagged_diameter = 0

    pdf_files = sorted(glob.glob('data/pravo_pdfs/*.pdf'))
    print(f"Found {len(pdf_files)} downloaded PDFs ready for analysis.")

    for pdf_path in pdf_files:
        p0 = os.path.basename(pdf_path).replace('.pdf', '')
        decree_meta = decrees_list.get(p0, {})
        title_meta = decree_meta.get('title', '')
        
        try:
            doc = pymupdf.open(pdf_path)
        except Exception as e:
            continue
            
        full_text = ""
        page_texts = []
        for page in doc:
            ptxt = page.get_text()
            page_texts.append(ptxt)
            full_text += ptxt + "\n"

        # 1. Extract coordinates across all pages
        all_points = {}
        for ptxt in page_texts:
            pts = parse_points_from_page(ptxt)
            for pt_num, coord in pts.items():
                if pt_num not in all_points:
                    all_points[pt_num] = coord

        if not all_points:
            continue

        total_decrees_with_coords += 1

        # 2. Extract codes
        raw_codes = re.findall(r'\b[1-7][0-3][0-3][А-Яа-яA-Za-z][0-9]{6}\b', full_text)
        codes = sorted(list(set([normalize_code(c) for c in raw_codes])))

        # 3. Isolate territory chapter and parse clauses
        ch_text, ch_type = isolate_territory_chapter(full_text)
        clauses = parse_boundary_clauses(ch_text, set(all_points.keys()))

        decree_entry = {
            "p0": p0,
            "title": title_meta,
            "codes": codes,
            "points_count": len(all_points),
            "chapter_type": ch_type,
            "clauses_count": len(clauses),
            "points": [{"num": k, "lat": round(v[0], 6), "lon": round(v[1], 6)} for k, v in sorted(all_points.items())]
        }
        processed_decrees[p0] = decree_entry

        # 4. Handle monument mapping
        # SPECIAL CASE: Trostenets W22543162p
        if p0 == 'W22543162p' and '711Д000283' in codes:
            code = '711Д000283'
            pts_primary = [p for p in range(1, 37) if p in all_points]
            pts_blagov = [p for p in range(40, 48) if p in all_points]
            lats = [all_points[p][0] for p in pts_primary]
            lons = [all_points[p][1] for p in pts_primary]
            c_lat = round(sum(lats) / len(lats), 6)
            c_lon = round(sum(lons) / len(lons), 6)
            
            b_diam = haversine_distance(min(lats), min(lons), max(lats), max(lons))
            blagov_c_lat = round(sum(all_points[p][0] for p in pts_blagov) / len(pts_blagov), 6)
            blagov_c_lon = round(sum(all_points[p][1] for p in pts_blagov) / len(pts_blagov), 6)
            
            mon = monuments_by_code.get(code)
            item = {
                'monument_id': mon.get('id', '') if mon else '',
                'code': code,
                'title': mon.get('t', '') if mon else 'Тэрыторыя былога лагера смерці «Трасцянец»',
                'type': mon.get('tp', '') if mon else '',
                'district': mon.get('dst', '') if mon else '',
                'locality': mon.get('loc', '') if mon else '',
                'decree_p0': p0,
                'decree_title': title_meta,
                'pravo_lat': c_lat,
                'pravo_lon': c_lon,
                'territory_points_used': len(pts_primary),
                'territory_point_indices': pts_primary,
                'bbox_diameter_meters': round(b_diam, 1),
                'flagged_large_diameter': b_diam > 2500,
                'secondary_parts': [{
                    'name': 'Урочышча Благаўшчына',
                    'points_used': len(pts_blagov),
                    'point_indices': pts_blagov,
                    'centroid': {'lat': blagov_c_lat, 'lon': blagov_c_lon}
                }],
                'total_points_in_decree': len(all_points),
                'status': 'new_coordinates',
                'description': 'Previously lacked coordinates in catalog. High-precision centroid extracted for primary memorial territory (Gate of Memory, pts 1-36). Disjoint Blagovshchina pits (pts 40-47) cataloged separately.'
            }
            total_new_coords_found += 1
            matched_results.append(item)
            continue

        # GENERAL CASE: Single-code decree
        if len(codes) == 1:
            code = codes[0]
            mon = monuments_by_code.get(code)
            if not mon and len(code) == 10:
                mon = monuments_by_prefix_suffix.get((code[0], code[3], code[4:]))
            if not mon:
                continue

            terr_pts = []
            for cl in clauses:
                terr_pts.extend(cl['points'])
            terr_pts = sorted(list(set(terr_pts)))

            inline_c = []
            for cl in clauses:
                inline_c.extend(cl['inline_coords'])

            coords = [all_points[p] for p in terr_pts if p in all_points]
            if not coords and inline_c:
                coords = inline_c
            if not coords:
                if ch_type == 'protection_zone':
                    coords = list(all_points.values())
                    terr_pts = list(all_points.keys())
                else:
                    continue

            lats = [c[0] for c in coords]
            lons = [c[1] for c in coords]
            c_lat = round(sum(lats) / len(lats), 6)
            c_lon = round(sum(lons) / len(lons), 6)
            b_diam = haversine_distance(min(lats), min(lons), max(lats), max(lons))
            flag_diam = b_diam > 2500
            if flag_diam:
                total_flagged_diameter += 1

            item = {
                'monument_id': mon.get('id', ''),
                'code': code,
                'title': mon.get('t', ''),
                'type': mon.get('tp', ''),
                'district': mon.get('dst', ''),
                'locality': mon.get('loc', ''),
                'decree_p0': p0,
                'decree_title': title_meta,
                'pravo_lat': c_lat,
                'pravo_lon': c_lon,
                'territory_points_used': len(coords),
                'territory_point_indices': terr_pts,
                'bbox_diameter_meters': round(b_diam, 1),
                'flagged_large_diameter': flag_diam,
                'total_points_in_decree': len(all_points)
            }

            old_lat = mon.get('lat')
            old_lon = mon.get('lon')
            if old_lat is None or old_lon is None:
                item['status'] = 'new_coordinates'
                desc = 'Previously lacked coordinates in catalog. Exact coordinates extracted from official decree.'
                if flag_diam:
                    desc += f' [WARNING: Bounding box diameter {b_diam:.0f}m > 2.5km]'
                item['description'] = desc
                total_new_coords_found += 1
            else:
                d_dist = haversine_distance(old_lat, old_lon, c_lat, c_lon)
                item['old_lat'] = old_lat
                item['old_lon'] = old_lon
                item['distance_diff_meters'] = round(d_dist, 1)
                ckey = (round(old_lat, 4), round(old_lon, 4))
                cl_cnt = coord_counts.get(ckey, 1)

                if cl_cnt >= 3:
                    item['status'] = 'flagged_suspicious_heritage_gov_coords'
                    item['description'] = f'Suspicious coordinate cluster: old coordinates shared by {cl_cnt} monuments in heritage.gov.by. Discrepancy is {d_dist:.0f}m. Exact protection zone centroid recommended.'
                    total_suspicious_flagged += 1
                elif d_dist > 500:
                    item['status'] = 'discrepancy_detected'
                    item['description'] = f'Significant discrepancy detected ({d_dist:.0f}m from base dataset). Decree protection zone centroid is high-precision.'
                else:
                    item['status'] = 'verified_existing_coords'
                    item['description'] = f'Existing coordinates verified against official decree (difference: {d_dist:.0f}m).'
                    total_verified_coords += 1
                if flag_diam:
                    item['description'] += f' [WARNING: Bounding box diameter {b_diam:.0f}m > 2.5km]'

            matched_results.append(item)

        # GENERAL CASE: Multi-code decree
        else:
            for code in codes:
                mon = monuments_by_code.get(code)
                if not mon and len(code) == 10:
                    mon = monuments_by_prefix_suffix.get((code[0], code[3], code[4:]))
                if not mon:
                    continue

                best_cl, score = match_monument_to_clause(code, mon, clauses)
                if not best_cl or score < 45.0 or not best_cl['points']:
                    continue

                pts = best_cl['points']
                coords = [all_points[p] for p in pts if p in all_points]
                if not coords:
                    continue

                lats = [c[0] for c in coords]
                lons = [c[1] for c in coords]
                c_lat = round(sum(lats) / len(lats), 6)
                c_lon = round(sum(lons) / len(lons), 6)
                b_diam = haversine_distance(min(lats), min(lons), max(lats), max(lons))
                flag_diam = b_diam > 2500
                if flag_diam:
                    total_flagged_diameter += 1

                item = {
                    'monument_id': mon.get('id', ''),
                    'code': code,
                    'title': mon.get('t', ''),
                    'type': mon.get('tp', ''),
                    'district': mon.get('dst', ''),
                    'locality': mon.get('loc', ''),
                    'decree_p0': p0,
                    'decree_title': title_meta,
                    'pravo_lat': c_lat,
                    'pravo_lon': c_lon,
                    'territory_points_used': len(coords),
                    'territory_point_indices': pts,
                    'bbox_diameter_meters': round(b_diam, 1),
                    'flagged_large_diameter': flag_diam,
                    'total_points_in_decree': len(all_points),
                    'clause_match_score': round(score, 1)
                }

                old_lat = mon.get('lat')
                old_lon = mon.get('lon')
                if old_lat is None or old_lon is None:
                    item['status'] = 'new_coordinates'
                    desc = 'Previously lacked coordinates in catalog. Exact coordinates extracted from official decree.'
                    if flag_diam:
                        desc += f' [WARNING: Bounding box diameter {b_diam:.0f}m > 2.5km]'
                    item['description'] = desc
                    total_new_coords_found += 1
                else:
                    d_dist = haversine_distance(old_lat, old_lon, c_lat, c_lon)
                    item['old_lat'] = old_lat
                    item['old_lon'] = old_lon
                    item['distance_diff_meters'] = round(d_dist, 1)
                    ckey = (round(old_lat, 4), round(old_lon, 4))
                    cl_cnt = coord_counts.get(ckey, 1)

                    if cl_cnt >= 3:
                        item['status'] = 'flagged_suspicious_heritage_gov_coords'
                        item['description'] = f'Suspicious coordinate cluster: old coordinates shared by {cl_cnt} monuments in heritage.gov.by. Discrepancy is {d_dist:.0f}m. Exact protection zone centroid recommended.'
                        total_suspicious_flagged += 1
                    elif d_dist > 500:
                        item['status'] = 'discrepancy_detected'
                        item['description'] = f'Significant discrepancy detected ({d_dist:.0f}m from base dataset). Decree protection zone centroid is high-precision.'
                    else:
                        item['status'] = 'verified_existing_coords'
                        item['description'] = f'Existing coordinates verified against official decree (difference: {d_dist:.0f}m).'
                        total_verified_coords += 1
                    if flag_diam:
                        item['description'] += f' [WARNING: Bounding box diameter {b_diam:.0f}m > 2.5km]'

                matched_results.append(item)

    # Save to data/pravo_heritage_protection_zones_v2.json
    output_data = {
        "metadata": {
            "source": "National Legal Internet Portal of the Republic of Belarus (pravo.by)",
            "purpose": "High-precision GPS coordinates mining from official protection zone decrees (v2: strictly territory clauses, monument point slicing, false centroid avoidance)",
            "date_generated": "2026-09-27",
            "version": "2.0",
            "total_decrees_analyzed": len(pdf_files),
            "decrees_with_coordinate_tables": total_decrees_with_coords,
            "monuments_matched": len(matched_results),
            "new_coordinates_discovered": total_new_coords_found,
            "flagged_suspicious_heritage_gov_coords": total_suspicious_flagged,
            "verified_existing_coords": total_verified_coords,
            "flagged_large_diameter_count": total_flagged_diameter
        },
        "matched_monuments": matched_results,
        "protection_zone_decrees": processed_decrees
    }

    with open('data/pravo_heritage_protection_zones_v2.json', 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    print("\n" + "="*60)
    print("EXTRACTION AND SPATIAL ANALYSIS COMPLETE (v2)")
    print("="*60)
    print(f"Total PDFs analyzed: {len(pdf_files)}")
    print(f"Decrees with coordinate tables: {total_decrees_with_coords}")
    print(f"Total monuments matched: {len(matched_results)}")
    print(f"✨ NEW COORDINATES DISCOVERED: {total_new_coords_found}")
    print(f"🚨 FLAGGED SUSPICIOUS CLUSTERS (heritage.gov.by): {total_suspicious_flagged}")
    print(f"✅ Verified existing coordinates: {total_verified_coords}")
    print(f"⚠️ Flagged large diameter (>2.5 km): {total_flagged_diameter}")
    print("Results saved to: data/pravo_heritage_protection_zones_v2.json")

if __name__ == '__main__':
    main()
