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
    # Normalize 4th character if it's Latin lookalike
    if len(code_str) >= 4:
        c4 = code_str[3]
        if c4 in CYR_LAT_MAP:
            code_str = code_str[:3] + CYR_LAT_MAP[c4] + code_str[4:]
    return code_str

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
    # e.g.: 1 53.394867, 24.804681 or 1 53,394867 24,804681
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
        # Check if line is just a point number, and next line has "lat, lon"
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
            # Or if line+1 is lat, line+2 is lon
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

def extract_territory_point_indices(full_text):
    """
    Examines Chapter 2 / «Мяжой тэрыторыі гісторыка-культурнай каштоўнасці...»
    to determine which point indices belong to the monument's territory.
    """
    territory_points = set()
    
    # Search for paragraph defining territory boundary
    patterns = [
        r'(?:Мяжой|Межамі)\s+тэрыторыі[^.]+?(?:праз\s+кропкі|ад\s+кропкі)[^.]+',
        r'ТЭРЫТОРЫЯ\s+ГІСТОРЫКА-КУЛЬТУРНАЙ\s+КАШТОЎНАСЦІ[^.]+?(?:праз\s+кропкі|ад\s+кропкі)[^.]+'
    ]
    
    found_snippets = []
    for pat in patterns:
        for m in re.finditer(pat, full_text, re.DOTALL | re.IGNORECASE):
            found_snippets.append(m.group(0))
            
    for snip in found_snippets:
        # Match sequences like 1–2–3–4–1 or 1-2-3 or 1-10 or 1, 2, 3
        # Match "праз кропкі 1–... да кропкі 1"
        pt_matches = re.findall(r'(\d+)\s*[-–—]\s*(\d+)', snip)
        for p_start, p_end in pt_matches:
            s, e = int(p_start), int(p_end)
            if s <= e and e - s < 100:
                for k in range(s, e + 1):
                    territory_points.add(k)
        # Also all single point numbers in the snippet after "кропкі"
        after_kropki = re.findall(r'(?:кропкі|кропку|кропак)\s+([0-9\s,\-–—іда]+)', snip)
        for chunk in after_kropki:
            for num in re.findall(r'\b\d{1,4}\b', chunk):
                territory_points.add(int(num))

    return sorted(list(territory_points))

def main():
    print("Loading base monuments dataset from data/monuments.json...")
    with open('data/monuments.json', encoding='utf-8') as f:
        monuments_list = json.load(f)
    print(f"Loaded {len(monuments_list)} monuments.")

    # Build lookup by code and check coordinate clustering
    monuments_by_code = {}
    monuments_by_prefix_suffix = {} # (region, type_letter, suffix_digits)
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

    pdf_files = glob.glob('data/pravo_pdfs/*.pdf')
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

        # 1. Extract codes
        raw_codes = re.findall(r'\b[1-7][0-3][0-3][А-Яа-яA-Za-z][0-9]{6}\b', full_text)
        codes = list(set([normalize_code(c) for c in raw_codes]))

        # 2. Extract coordinates across all pages
        all_points = {}
        for p_idx, ptxt in enumerate(page_texts):
            # Check if page has coordinates table
            pts = parse_points_from_page(ptxt)
            for pt_num, coord in pts.items():
                if pt_num not in all_points:
                    all_points[pt_num] = coord

        if not all_points:
            # Decree does not have explicit coordinate table
            continue

        total_decrees_with_coords += 1

        # 3. Determine territory points
        territory_indices = extract_territory_point_indices(full_text)
        territory_coords = []
        if territory_indices:
            for idx in territory_indices:
                if idx in all_points:
                    territory_coords.append(all_points[idx])
        
        # If no specific territory points identified, use all points
        if not territory_coords:
            territory_coords = list(all_points.values())

        # 4. Calculate centroid
        centroid_lat = sum(p[0] for p in territory_coords) / len(territory_coords)
        centroid_lon = sum(p[1] for p in territory_coords) / len(territory_coords)
        centroid_lat = round(centroid_lat, 6)
        centroid_lon = round(centroid_lon, 6)

        decree_entry = {
            "p0": p0,
            "title": title_meta,
            "codes": codes,
            "points_count": len(all_points),
            "territory_points_count": len(territory_coords),
            "centroid": {"lat": centroid_lat, "lon": centroid_lon},
            "points": [{"num": k, "lat": round(v[0], 6), "lon": round(v[1], 6)} for k, v in sorted(all_points.items())],
            "territory_point_numbers": territory_indices
        }
        processed_decrees[p0] = decree_entry

        # 5. Match with monuments.json
        for code in codes:
            monument = monuments_by_code.get(code)
            if not monument and len(code) == 10:
                key = (code[0], code[3], code[4:])
                monument = monuments_by_prefix_suffix.get(key)
            if not monument:
                continue

                
            curr_lat = monument.get('lat')
            curr_lon = monument.get('lon')
            m_title = monument.get('t', '')
            m_id = monument.get('id', '')
            m_loc = monument.get('loc', '')
            m_dst = monument.get('dst', '')
            m_tp = monument.get('tp', '')

            result_item = {
                "monument_id": m_id,
                "code": code,
                "title": m_title,
                "type": m_tp,
                "district": m_dst,
                "locality": m_loc,
                "decree_p0": p0,
                "decree_title": title_meta,
                "pravo_lat": centroid_lat,
                "pravo_lon": centroid_lon,
                "territory_points_used": len(territory_coords),
                "total_points_in_decree": len(all_points)
            }

            if curr_lat is None or curr_lon is None:
                # NEW COORDINATES!
                result_item["status"] = "new_coordinates"
                result_item["description"] = "Previously lacked coordinates in catalog. Exact coordinates extracted from official decree."
                total_new_coords_found += 1
            else:
                dist_m = haversine_distance(curr_lat, curr_lon, centroid_lat, centroid_lon)
                result_item["old_lat"] = curr_lat
                result_item["old_lon"] = curr_lon
                result_item["distance_diff_meters"] = round(dist_m, 1)

                coord_key = (round(curr_lat, 4), round(curr_lon, 4))
                cluster_count = coord_counts.get(coord_key, 1)

                if cluster_count >= 3:
                    # Blanket / suspicious heritage.gov.by cluster!
                    result_item["status"] = "flagged_suspicious_heritage_gov_coords"
                    result_item["description"] = f"Suspicious coordinate cluster: old coordinates shared by {cluster_count} monuments in heritage.gov.by. Discrepancy is {dist_m:.0f}m. Exact protection zone centroid recommended."
                    total_suspicious_flagged += 1
                elif dist_m > 500:
                    result_item["status"] = "discrepancy_detected"
                    result_item["description"] = f"Significant discrepancy detected ({dist_m:.0f}m from base dataset). Decree protection zone centroid is high-precision."
                else:
                    result_item["status"] = "verified_existing_coords"
                    result_item["description"] = f"Existing coordinates verified against official decree (difference: {dist_m:.0f}m)."
                    total_verified_coords += 1

            matched_results.append(result_item)

    # Save to data/pravo_heritage_protection_zones.json
    output_data = {
        "metadata": {
            "source": "National Legal Internet Portal of the Republic of Belarus (pravo.by)",
            "purpose": "High-precision GPS coordinates mining from official protection zone decrees",
            "date_generated": "2026-09-27",
            "total_decrees_analyzed": len(pdf_files),
            "decrees_with_coordinate_tables": total_decrees_with_coords,
            "monuments_matched": len(matched_results),
            "new_coordinates_discovered": total_new_coords_found,
            "flagged_suspicious_heritage_gov_coords": total_suspicious_flagged,
            "verified_existing_coords": total_verified_coords
        },
        "matched_monuments": matched_results,
        "protection_zone_decrees": processed_decrees
    }

    with open('data/pravo_heritage_protection_zones.json', 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    print("\n" + "="*60)
    print("EXTRACTION AND SPATIAL ANALYSIS COMPLETE")
    print("="*60)
    print(f"Total PDFs analyzed: {len(pdf_files)}")
    print(f"Decrees with coordinate tables: {total_decrees_with_coords}")
    print(f"Total monuments matched: {len(matched_results)}")
    print(f"✨ NEW COORDINATES DISCOVERED: {total_new_coords_found}")
    print(f"🚨 FLAGGED SUSPICIOUS CLUSTERS (heritage.gov.by): {total_suspicious_flagged}")
    print(f"✅ Verified existing coordinates: {total_verified_coords}")
    print("Results saved to: data/pravo_heritage_protection_zones.json")

if __name__ == '__main__':
    main()
