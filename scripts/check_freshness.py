"""
Controleert of de provider-tarieven nog actueel zijn.
Waarschuwt als return_verified/rate_verified ouder is dan 90 dagen,
en als affiliate_url ontbreekt/ongeldig is terwijl affiliate_network is gezet.
Werkt de last_updated datum bij in providers.json.
"""
import json
import sys
from datetime import date, datetime

PROVIDERS_FILE = 'providers.json'
MAX_AGE_DAYS = 90

def check_dynamic(key, info, today):
    verified_str = info.get('return_verified')
    if not verified_str:
        return f"  - {key}: geen return_verified datum"

    try:
        verified_date = datetime.strptime(verified_str, '%Y-%m-%d').date()
        age = (today - verified_date).days
        if age > MAX_AGE_DAYS:
            return (
                f"  - {key} ({info['name']}): return_cost={info.get('return_cost', '?')} "
                f"— laatste verificatie {age} dagen geleden ({verified_str})"
            )
    except ValueError:
        return f"  - {key}: ongeldige datum '{verified_str}'"
    return None

def check_fixed(key, info, today):
    verified_str = info.get('rate_verified')
    if not verified_str:
        return f"  - {key}: geen rate_verified datum"

    try:
        verified_date = datetime.strptime(verified_str, '%Y-%m-%d').date()
        age = (today - verified_date).days
        if age > MAX_AGE_DAYS:
            return (
                f"  - {key} ({info['name']}, {info.get('contract_term_months', '?')} mnd): "
                f"— laatste verificatie {age} dagen geleden ({verified_str})"
            )
    except ValueError:
        return f"  - {key}: ongeldige datum '{verified_str}'"
    return None

def check_affiliate_url(key, info):
    if not info.get('affiliate_network'):
        return None
    url = info.get('affiliate_url')
    if not url or not url.startswith('https://'):
        return f"  - {key}: affiliate_network='{info['affiliate_network']}' maar affiliate_url ontbreekt/ongeldig ('{url}')"
    return None

def main():
    with open(PROVIDERS_FILE, 'r') as f:
        data = json.load(f)

    today = date.today()
    warnings = []

    for key, info in data.items():
        if key.startswith('_'):
            continue

        if info.get('type') == 'DYNAMIC':
            w = check_dynamic(key, info, today)
            if w:
                warnings.append(w)
        elif info.get('type') == 'FIXED':
            w = check_fixed(key, info, today)
            if w:
                warnings.append(w)

        w = check_affiliate_url(key, info)
        if w:
            warnings.append(w)

    # Bijwerken last_updated
    if '_meta' in data:
        data['_meta']['last_updated'] = str(today)
        with open(PROVIDERS_FILE, 'w') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        print(f"✅ last_updated bijgewerkt naar {today}")

    if warnings:
        print(f"\n⚠️  {len(warnings)} provider(s) met verouderde teruglevertarieven (>{MAX_AGE_DAYS} dagen):")
        for w in warnings:
            print(w)
        print("\nActie vereist: controleer de tarieven op de websites van deze aanbieders")
        print("en pas return_cost + return_verified bij in providers.json.\n")
        # Geen sys.exit(1) — we willen de workflow niet laten falen, alleen waarschuwen
    else:
        print(f"✅ Alle teruglevertarieven zijn actueel (geverifieerd binnen {MAX_AGE_DAYS} dagen)")

if __name__ == '__main__':
    main()
