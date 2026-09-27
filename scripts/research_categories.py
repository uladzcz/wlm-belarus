import json
import sys
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding='utf-8')

headers = {'User-Agent': 'WlmBelarusResearch/1.0 (contact: bafur)'}

def api(params):
    url = 'https://commons.wikimedia.org/w/api.php?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode('utf-8'))

# 1. Search for ID categories in various countries
countries = ['Ukraine', 'Poland', 'Armenia', 'Russia', 'France', 'Germany', 'Spain', 'Belarus']
print("=== 1. Categories matching 'heritage ID' ===")
for c in countries:
    data = api({
        'action': 'query',
        'list': 'search',
        'srsearch': f'intitle:"heritage ID" {c}',
        'srnamespace': 14,
        'srlimit': 5,
        'format': 'json'
    })
    results = [r['title'] for r in data.get('query', {}).get('search', [])]
    print(f"{c}: {results}")

# 2. Check how WLM UploadWizard is configured for other countries
# e.g., campaign wlm-by, wlm-ua, wlm-pl, wlm-ru
print("\n=== 2. Check WLM campaigns config on Commons ===")
for campaign in ['wlm-by', 'wlm-ua', 'wlm-pl', 'wlm-ru']:
    title = f'Commons:Upload_Campaign/config/{campaign}'
    data = api({
        'action': 'query',
        'prop': 'revisions',
        'titles': title,
        'rvprop': 'content',
        'format': 'json'
    })
    pages = data.get('query', {}).get('pages', {})
    for pid, p in pages.items():
        if 'missing' in p:
            print(f"{campaign}: config page not found")
        else:
            content = p.get('revisions', [{}])[0].get('*', '')
            # find defaultCategory or categories
            print(f"{campaign}: page length {len(content)}")
            for line in content.splitlines():
                if 'categor' in line.lower() or 'template' in line.lower():
                    print(f"   {line[:120]}")

# 3. Check existing district and city categories in Belarus
print("\n=== 3. District and City categories for Belarus ===")
for parent in [
    'Category:Cultural heritage monuments in Belarus by district',
    'Category:Cultural heritage monuments in Belarus by city',
    'Category:Cultural heritage monuments in Belarus by region'
]:
    data = api({
        'action': 'query',
        'list': 'categorymembers',
        'cmtitle': parent,
        'cmtype': 'subcat',
        'cmlimit': 500,
        'format': 'json'
    })
    subcats = [m['title'] for m in data.get('query', {}).get('categorymembers', [])]
    print(f"{parent}: {len(subcats)} subcategories")
    for s in subcats[:10]:
        print(f"   {s}")
