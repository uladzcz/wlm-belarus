import urllib.request
import urllib.parse
import re
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

search_terms = [
    'праекта зон аховы',
    'праекта зоны аховы',
    'праект зон аховы',
    'зон аховы нерухомай',
    'зон аховы курганнага',
    'зон аховы гарадзішча',
    'зон аховы селішча',
    'зон аховы брацкай',
    'зон аховы помніка',
]

all_docs = {}

for term in search_terms:
    print(f"\n=== Searching term: '{term}' ===")
    p2 = 0
    consecutive_empty = 0
    term_count = 0
    while True:
        url = f'https://pravo.by/natsionalnyy-reestr/poisk-v-reestre/?p0={urllib.parse.quote(term)}&p2={p2}'
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                html = resp.read().decode('utf-8', errors='ignore')
            
            # Find document links
            # Link pattern: /document/?guid=3961&amp;p0=W22644767p or similar
            matches = re.findall(r'<a[^>]*href=["\'](/document/[^"\']*p0=([A-Za-z0-9]+)[^"\']*)["\'][^>]*>(.*?)</a>', html, re.DOTALL)
            if not matches:
                # Let's check if there are no results or end of pages
                break
            
            new_in_page = 0
            for href, p0, title_html in matches:
                clean_title = re.sub(r'<[^>]+>', '', title_html).strip()
                if p0 not in all_docs:
                    all_docs[p0] = {
                        'p0': p0,
                        'title': clean_title,
                        'term': term,
                        'p2': p2
                    }
                    new_in_page += 1
                    term_count += 1
            
            # Check pagination HTML to know if there's a next page
            # If the page has no new items or < 10 docs or if p2 is beyond total pages
            if len(matches) < 10 or new_in_page == 0:
                consecutive_empty += 1
                if consecutive_empty >= 2:
                    break
            else:
                consecutive_empty = 0
            
            # Pravo.by pagination links: data-page="X#paging"
            max_p2 = 0
            for dp in re.findall(r'data-page=["\'](\d+)#paging["\']', html):
                max_p2 = max(max_p2, int(dp))
            
            if p2 >= max_p2 and max_p2 > 0:
                break
            
            p2 += 1
            time.sleep(0.2)
        except Exception as e:
            print(f"  Error on p2={p2}: {e}")
            break
            
    print(f"Term '{term}' yielded {term_count} documents (Total unique so far: {len(all_docs)})")

print(f"\nTOTAL UNIQUE DECREES FOUND: {len(all_docs)}")

# Save list of found decrees
import json
with open('data/pravo_decrees_list.json', 'w', encoding='utf-8') as f:
    json.dump(all_docs, f, ensure_ascii=False, indent=2)
print("Saved list to data/pravo_decrees_list.json")
