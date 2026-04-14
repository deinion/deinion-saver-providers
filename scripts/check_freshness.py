"""
Controleert of de provider-tarieven nog actueel zijn.
Waarschuwt als return_verified ouder is dan 90 dagen.
Werkt de last_updated datum bij in providers.json.
"""
import json
import sys
from datetime import date, datetime

PROVIDERS_FILE = 'providers.json'
MAX_AGE_DAYS = 90

def main():
    with open(PROVIDERS_FILE, 'r') as f:
        data = json.load(f)

    today = date.today()
    warnings = []

    for key, info in data.items():
        if key.startswith('_'):
            continue
        if info.get('type') != 'DYNAMIC':
            continue

        verified_str = info.get('return_verified')
        if not verified_str:
            warnings.append(f"  - {key}: geen return_verified datum")
            continue

        try:
            verified_date = datetime.strptime(verified_str, '%Y-%m-%d').date()
            age = (today - verified_date).days
            if age > MAX_AGE_DAYS:
                warnings.append(
                    f"  - {key} ({info['name']}): return_cost={info.get('return_cost', '?')} "
                    f"— laatste verificatie {age} dagen geleden ({verified_str})"
                )
        except ValueError:
            warnings.append(f"  - {key}: ongeldige datum '{verified_str}'")

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
