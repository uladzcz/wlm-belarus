import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('data/pravo_heritage_protection_zones.json', encoding='utf-8') as f:
    data = json.load(f)

meta = data['metadata']
print("=== METADATA ===")
for k, v in meta.items():
    print(f"  {k}: {v}")

matched = data['matched_monuments']
new_coords = [m for m in matched if m['status'] == 'new_coordinates']
suspicious = [m for m in matched if m['status'] == 'flagged_suspicious_heritage_gov_coords']
discrepant = [m for m in matched if m['status'] == 'discrepancy_detected']
verified = [m for m in matched if m['status'] == 'verified_existing_coords']

print(f"\nBreakdown:")
print(f"  New Coordinates: {len(new_coords)}")
print(f"  Flagged Suspicious Clusters (heritage.gov.by): {len(suspicious)}")
print(f"  Significant Discrepancies (>500m): {len(discrepant)}")
print(f"  Verified (<500m): {len(verified)}")

print("\n--- NEW COORDINATES BY TYPE ---")
types = {}
for m in new_coords:
    t = m.get('type') or 'Невядома'
    types[t] = types.get(t, 0) + 1
for t, c in sorted(types.items(), key=lambda x: -x[1]):
    print(f"  {t}: {c}")

print(f"\n--- ALL {len(new_coords)} NEWLY MAPPED MONUMENTS ---")
for i, m in enumerate(new_coords):
    print(f"{i+1:2d}. [{m['code']}] {m.get('type','')} | {m.get('title','')} | {m.get('locality','')} ({m.get('district','')}) -> GPS: {m['pravo_lat']}, {m['pravo_lon']} (points: {m['territory_points_used']})")


print("\n--- FLAGGED SUSPICIOUS CLUSTERS (heritage.gov.by) ---")
for m in suspicious:
    print(f"  [{m['code']}] {m.get('type','')} | {m.get('title','')} | {m.get('locality','')} ({m.get('district','')})")
    print(f"      Old heritage.gov.by: {m['old_lat']}, {m['old_lon']}")
    print(f"      Official Pravo.by  : {m['pravo_lat']}, {m['pravo_lon']}")
    print(f"      Discrepancy offset : {m['distance_diff_meters']} m")
    print(f"      Note: {m['description']}")
