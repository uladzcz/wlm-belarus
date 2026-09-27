import urllib.request
import re
import os
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import sys

sys.stdout.reconfigure(encoding='utf-8')
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}

os.makedirs('data/pravo_pdfs', exist_ok=True)

with open('data/pravo_decrees_list.json', encoding='utf-8') as f:
    decrees = json.load(f)

print(f"Loaded {len(decrees)} decrees from list.")

def get_pdf(p0):
    pdf_path = f"data/pravo_pdfs/{p0}.pdf"
    if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 1000:
        return (p0, True, "cached", os.path.getsize(pdf_path))
    
    viewer_url = f"https://pravo.by/document/?guid=12551&p0={p0}"
    try:
        req = urllib.request.Request(viewer_url, headers=headers)
        with urllib.request.urlopen(req, timeout=20) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
        matches = re.findall(r'(/upload/docs/op/[^\'"\s>]+\.pdf)', html)
        if not matches:
            return (p0, False, "no_pdf_link", 0)
        
        pdf_url = "https://pravo.by" + matches[0]
        req_pdf = urllib.request.Request(pdf_url, headers=headers)
        with urllib.request.urlopen(req_pdf, timeout=30) as resp_pdf:
            data = resp_pdf.read()
        
        with open(pdf_path, 'wb') as f:
            f.write(data)
        return (p0, True, "downloaded", len(data))
    except Exception as e:
        return (p0, False, str(e), 0)

# Run with 4 threads
success_count = 0
failed = []
start_time = time.time()

print("Starting download of PDFs with 4 threads...")
with ThreadPoolExecutor(max_workers=4) as executor:
    futures = {executor.submit(get_pdf, p0): p0 for p0 in decrees.keys()}
    done_count = 0
    for future in as_completed(futures):
        p0, ok, msg, size = future.result()
        done_count += 1
        if ok:
            success_count += 1
        else:
            failed.append((p0, msg))
        
        if done_count % 25 == 0 or done_count == len(decrees):
            elapsed = time.time() - start_time
            print(f"Progress: {done_count}/{len(decrees)} ({success_count} success, {len(failed)} failed) in {elapsed:.1f}s", flush=True)

print(f"\nFinished! Total downloaded/cached: {success_count}/{len(decrees)}")
if failed:
    print(f"Failed count: {len(failed)} (sample: {failed[:5]})")
