"""
fetch_prices.py
Wordt dagelijks uitgevoerd door GitHub Actions.
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
from zoneinfo import ZoneInfo

PRICES_FILE = 'dynamic_prices.json'
API_URL = 'https://api.energyzero.nl/v1/energyprices'
MAX_RETRIES = 5
RETRY_DELAY = 300  # 5 minuten tussen pogingen
MIN_TOMORROW_PRICES = 24

def log(msg):
    print(f"[{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC] {msg}")

def get_amsterdam_tomorrow_window():
    """Geeft het UTC-tijdvenster van morgen in Amsterdam-tijd terug + verwacht aantal uren.

    Normale dag: 24 uren. Lenteovergang: 23 uren. Herfstovergang: 25 uren.
    """
    amsterdam = ZoneInfo('Europe/Amsterdam')
    now_ams = datetime.now(amsterdam)
    tomorrow_ams_start = (now_ams + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0)
    day_after_ams_start = (now_ams + timedelta(days=2)).replace(
        hour=0, minute=0, second=0, microsecond=0)
    start_utc    = tomorrow_ams_start.astimezone(timezone.utc)
    end_utc      = day_after_ams_start.astimezone(timezone.utc)
    expected     = int((end_utc - start_utc).total_seconds() // 3600)
    return start_utc, end_utc, tomorrow_ams_start.strftime('%Y-%m-%d'), expected

def count_tomorrow_prices(prices):
    """Telt prijspunten die vallen binnen morgen (Amsterdam-tijd)."""
    start_utc, end_utc, _, expected = get_amsterdam_tomorrow_window()
    count = sum(
        1 for p in prices
        if start_utc <= datetime.fromisoformat(p['time'].replace('Z', '+00:00')) < end_utc
    )
    return count, expected

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
    # Gebruik Amsterdam-tijdzone voor datumberekeningen
    amsterdam = ZoneInfo('Europe/Amsterdam')
    now_ams = datetime.now(amsterdam)

    # Vraag data op voor vandaag én morgen (Amsterdam-tijd)
    # EnergyZero interpreteert de datums als Amsterdam lokale tijd
    start = now_ams.strftime('%Y-%m-%dT00:00:00.000Z')
    end   = (now_ams + timedelta(days=1)).strftime('%Y-%m-%dT23:59:59.999Z')

    log(f"Start prijzen ophalen voor {start[:10]} t/m {end[:10]} (Amsterdam)")

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
    data['updated_at'] = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')

    with open(PRICES_FILE, 'w') as f:
        json.dump(data, f, indent=4)

    tomorrow_count, expected = count_tomorrow_prices(data['electricity'])
    _, _, tomorrow_label, _ = get_amsterdam_tomorrow_window()
    log(f"✅ Opgeslagen: +{elec_added} elektriciteit, +{gas_added} gas "
        f"(totaal: {len(data['electricity'])} / {len(data['gas'])})")
    log(f"   Morgen ({tomorrow_label} Amsterdam): {tomorrow_count}/{expected} prijspunten aanwezig")

if __name__ == '__main__':
    main()
