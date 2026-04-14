"""
fetch_prices.py
Wordt dagelijks uitgevoerd door GitHub Actions om 13:15 UTC.
Haalt de day-ahead energieprijzen op van de EnergyZero API en
voegt ze toe aan dynamic_prices.json in de repo.

Bij een tijdelijke API-fout wordt tot 5x opnieuw geprobeerd.
"""
import requests
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

PRICES_FILE = 'dynamic_prices.json'
API_URL = 'https://api.energyzero.nl/v1/BROKEN_FOR_TEST'
MAX_RETRIES = 5
RETRY_DELAY = 300  # 5 minuten tussen pogingen

def log(msg):
    print(f"[{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC] {msg}")

def fetch_electricity(start, end):
    params = {
        'fromDate': start,
        'tillDate': end,
        'interval': 9,       # kwartierdata
        'usageType': 1,      # stroom
        'inclBtw': 'true'
    }
    resp = requests.get(API_URL, params=params, timeout=15,
                        headers={'User-Agent': 'DeinionSaver-GitHub/1.0'})
    resp.raise_for_status()
    data = resp.json()
    prices = data.get('Prices', [])
    if not prices:
        raise ValueError("API gaf lege Prices terug voor elektriciteit")
    return [{'time': p['readingDate'], 'price': p['price']} for p in prices]

def fetch_gas(start, end):
    params = {
        'fromDate': start,
        'tillDate': end,
        'interval': 4,
        'usageType': 2,
        'inclBtw': 'true'
    }
    resp = requests.get(API_URL, params=params, timeout=15,
                        headers={'User-Agent': 'DeinionSaver-GitHub/1.0'})
    resp.raise_for_status()
    data = resp.json()
    prices = data.get('Prices', [])
    return [{'time': p['readingDate'], 'price': p['price']} for p in prices]

def merge(existing, new_items):
    """Voegt nieuwe prijspunten toe aan bestaande lijst, geen duplicaten."""
    existing_times = {item['time'] for item in existing}
    added = 0
    for item in new_items:
        if item['time'] not in existing_times:
            existing.append(item)
            added += 1
    existing.sort(key=lambda x: x['time'])
    return existing, added

def main():
    now_utc = datetime.now(timezone.utc)
    # Haal prijzen op voor vandaag én morgen
    start = now_utc.strftime('%Y-%m-%dT00:00:00.000Z')
    end = (now_utc + timedelta(days=1)).strftime('%Y-%m-%dT23:59:59.999Z')

    log(f"Start prijzen ophalen voor {start[:10]} t/m {end[:10]}")

    # Laad bestaand bestand
    if os.path.exists(PRICES_FILE):
        with open(PRICES_FILE, 'r') as f:
            data = json.load(f)
    else:
        data = {'electricity': [], 'gas': []}

    # Fetch met retries
    elec_new, gas_new = None, None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            log(f"Poging {attempt}/{MAX_RETRIES}: elektriciteit ophalen...")
            elec_new = fetch_electricity(start, end)
            log(f"✅ {len(elec_new)} elektriciteitsprijzen opgehaald")

            log(f"Poging {attempt}/{MAX_RETRIES}: gasprijzen ophalen...")
            gas_new = fetch_gas(start, end)
            log(f"✅ {len(gas_new)} gasprijzen opgehaald")
            break

        except Exception as e:
            log(f"❌ Poging {attempt} mislukt: {e}")
            if attempt < MAX_RETRIES:
                log(f"Wacht {RETRY_DELAY // 60} minuten voor volgende poging...")
                time.sleep(RETRY_DELAY)
            else:
                log("Alle pogingen mislukt. Bestand ongewijzigd.")
                sys.exit(1)

    # Merge
    data['electricity'], elec_added = merge(data.get('electricity', []), elec_new)
    data['gas'], gas_added = merge(data.get('gas', []), gas_new)
    data['updated_at'] = now_utc.strftime('%Y-%m-%d %H:%M:%S')

    with open(PRICES_FILE, 'w') as f:
        json.dump(data, f, indent=4)

    log(f"✅ Opgeslagen: +{elec_added} elektriciteit, +{gas_added} gas "
        f"(totaal: {len(data['electricity'])} / {len(data['gas'])})")

if __name__ == '__main__':
    main()
