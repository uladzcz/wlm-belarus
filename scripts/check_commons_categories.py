import json
import sys
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding='utf-8')

# Search Commons for categories with ID schemes in WLM
queries = [
    'intitle:"WLM" intitle:"ID"',
    'intitle:"Cultural heritage monuments" "ID"',
    'intitle:"Cultural heritage monuments in Russia" "ID"',
    'intitle:"Cultural heritage monuments in Ukraine" "ID"',
    'intitle:"Cultural heritage monuments in Poland" "ID"',
    'intitle:"Historical and cultural values of Belarus"',
]

for q in queries:
    url = f'https://commons.wikimedia.org/w/api.php?action=query&list=search&srsearch={urllib.parse.quote(q)}&srnamespace=14&srlimit=10&format=json'
    req = urllib.request.Request(url, headers={'User-Agent': 'WlmBelarusBot/1.0'})
    try:
        data = json.load(urllib.request.urlopen(req))
        print(f'=== Query: {q} ===')
        for r in data.get('query', {}).get('search', []):
            print(' ', r['title'])
    except Exception as e:
        print(e)
