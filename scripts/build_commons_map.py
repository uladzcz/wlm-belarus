import json
import sys
import unicodedata

sys.path.append('../heritage-wrapper')
from scripts.translit import belarusian_to_latin

sys.stdout.reconfigure(encoding='utf-8')

with open('data/commons_heritage_categories.json', 'r', encoding='utf-8') as f:
    comm = json.load(f)

with open('data/monuments.json', 'r', encoding='utf-8') as f:
    monuments = json.load(f)

region_map = {
    'Брэсцкая вобласць': 'Cultural heritage monuments in Brest Region',
    'Віцебская вобласць': 'Cultural heritage monuments in Viciebsk Region',
    'Гомельская вобласць': 'Cultural heritage monuments in Gomel Region',
    'Гродзенская вобласць': 'Cultural heritage monuments in Hrodna Region',
    'Магілёўская вобласць': 'Cultural heritage monuments in Mahilioŭ region',
    'Мінская вобласць': 'Cultural heritage monuments in Minsk Region',
    'г. Мінск': 'Cultural heritage monuments in Minsk',
    'Мінск': 'Cultural heritage monuments in Minsk'
}

district_to_region = {}
for m in monuments:
    dst = m.get('dst')
    reg = m.get('r')
    if dst and reg:
        district_to_region[dst] = reg

district_cats = set(comm['districts'])
city_cats = set(comm['cities'])

def clean_norm(s):
    n = unicodedata.normalize('NFKD', s)
    return ''.join(c for c in n if not unicodedata.combining(c)).lower().replace(' ', '').replace('-', '').replace('\'', '').replace('’', '')

result = {}
result.update(region_map)

# Minsk city districts map to Minsk city category
minsk_districts = [
    'Кастрычніцкі раён', 'Завадскі раён', 'Ленінскі раён', 'Маскоўскі раён',
    'Партызанскі раён', 'Першамайскі раён', 'Савецкі раён', 'Фрунзенскі раён', 'Цэнтральны раён'
]
for md in minsk_districts:
    result[md] = 'Cultural heritage monuments in Minsk'

special = {
    'г. Віцебск': 'Cultural heritage monuments in Viciebsk',
    'г. Гродна': 'Cultural heritage monuments in Hrodna',
    'г. Брэст': 'Cultural heritage monuments in Brest, Belarus',
    'г. Гомель': 'Cultural heritage monuments in Gomel',
    'г. Магілёў': 'Cultural heritage monuments in Mahilioŭ',
    'г. Бабруйск': 'Cultural heritage monuments in Babrujsk',
    'г. Баранавічы': 'Cultural heritage monuments in Baranavičy',
    'г. Пінск': 'Cultural heritage monuments in Pinsk',
    'г. Наваполацк': 'Cultural heritage monuments in Navapolack',
    'г. Полацк': 'Cultural heritage monuments in Polack',
    'г. Жодзіна': 'Cultural heritage monuments in Žodzina',
    'Аршанскі раён': 'Cultural heritage monuments in Orša District',
    'Шчучынскі раён': 'Cultural heritage monuments in Ščučyn District',
    'Мсціслаўскі раён': 'Cultural heritage monuments in Mscislaŭ District',
    'Чавускі раён': 'Cultural heritage monuments in Čavusy District',
    'Клімавіцкі раён': 'Cultural heritage monuments in Klimavičy District',
    'Клічаўскі раён': 'Cultural heritage monuments in Kličaŭ District',
    'Касцюковіцкі раён': 'Cultural heritage monuments in Kasciukovičy District',
    'Гродзенскі раён': 'Cultural heritage monuments in Hrodna District',
    'Віцебскі раён': 'Cultural heritage monuments in Viciebsk District',
    'Брэсцкі раён': 'Cultural heritage monuments in Brest District',
    'Гомельскі раён': 'Cultural heritage monuments in Gomel District',
    'Магілёўскі раён': 'Cultural heritage monuments in Mogilev District',
    'Мінскі раён': 'Cultural heritage monuments in Minsk District',
    'Сенненскі раён': 'Cultural heritage monuments in Sianno District',
    'Свярдлоўскі раён': 'Cultural heritage monuments in Minsk Region',
}
result.update(special)

# Build map from transliterated root
district_cat_by_norm = {}
for dc in district_cats:
    core = dc.replace('Cultural heritage monuments in ', '').replace(' District', '')
    district_cat_by_norm[clean_norm(core)] = dc

city_cat_by_norm = {}
for cc in city_cats:
    core = cc.replace('Cultural heritage monuments in ', '').replace(', Belarus', '')
    city_cat_by_norm[clean_norm(core)] = cc

all_districts = set(m['dst'] for m in monuments if m.get('dst'))

for dst in all_districts:
    if dst in result:
        continue
    
    # Transliterate to Latin
    lat = belarusian_to_latin(dst).replace('rajon', '').replace('raën', '').replace('ski', '').replace('cki', '').strip()
    norm_lat = clean_norm(lat)
    
    matched = None
    if norm_lat in district_cat_by_norm:
        matched = district_cat_by_norm[norm_lat]
    elif norm_lat in city_cat_by_norm:
        matched = city_cat_by_norm[norm_lat]
    else:
        # substring match
        for k_norm, cat in district_cat_by_norm.items():
            if k_norm in norm_lat or norm_lat in k_norm:
                matched = cat
                break
                
    if not matched:
        reg = district_to_region.get(dst)
        matched = region_map.get(reg, 'Cultural heritage monuments in Belarus with known IDs')
        print(f"Fallback to region for: {dst} -> {matched}")
    else:
        print(f"Matched: {dst} -> {matched}")
        
    result[dst] = matched

print(f"Total mapped entries: {len(result)}")
with open('data/district_commons_map.json', 'w', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

print("Saved data/district_commons_map.json successfully!")
