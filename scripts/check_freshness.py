"""
Controleert de provider-tarieven op actualiteit en plausibiliteit.

Twee soorten bevindingen, met opzet verschillend behandeld:
  - WAARSCHUWING: data is oud (return_verified/rate_verified > 90 dagen). Vervelend, niet fataal.
  - FOUT: data is onmogelijk of onvolledig (daltarief boven normaaltarief, tarief buiten elke
    realistische bandbreedte, ontbrekende velden). Dit laat de workflow falen.

De reden voor dat onderscheid: een onmogelijk tarief levert een verkeerd bedrag op in de
kostenvergelijking, en daar sluit een gebruiker een meerjarig contract op af. Oud is te overzien,
fout is dat niet. Deze checks vangen ook het klassieke scraper-scenario af waarbij een layout-
wijziging het verkeerde veld oplevert (bv. een kaal leveringstarief i.p.v. all-in).

Werkt daarnaast de last_updated datum bij in providers.json.
"""
import json
import sys
from datetime import date, datetime

PROVIDERS_FILE = 'providers.json'
MAX_AGE_DAYS = 90

# Realistische bandbreedtes voor Nederlandse consumententarieven, INCL. energiebelasting en BTW.
# Ruim gekozen: bedoeld om grove fouten te vangen (kaal tarief i.p.v. all-in, eenheidsfout),
# niet om normale marktbewegingen af te keuren.
ELEC_BAND = (0.15, 0.45)   # EUR/kWh
GAS_BAND = (0.80, 2.50)    # EUR/m3
RETURN_BAND = (0.0, 0.30)  # EUR/kWh

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

def _in_band(value, band):
    return band[0] <= value <= band[1]

def check_fixed_plausibility(key, info):
    """Harde controles op FIXED-entries. Geeft een lijst fouten terug (leeg = goed)."""
    errors = []
    name = info.get('name', key)

    if not info.get('contract_term_months'):
        errors.append(f"  - {key} ({name}): contract_term_months ontbreekt")

    fp = info.get('fixed_prices')
    if not fp:
        errors.append(f"  - {key} ({name}): fixed_prices ontbreekt — kosten zijn niet te berekenen")
        return errors

    for field in ('elec_t1', 'elec_t2', 'gas'):
        if fp.get(field) is None:
            errors.append(f"  - {key} ({name}): fixed_prices.{field} ontbreekt")

    t1, t2 = fp.get('elec_t1'), fp.get('elec_t2')

    # Dal (T1) hoort nooit duurder te zijn dan normaal (T2). Zie create_db.py: t1=Dal, t2=Normaal.
    # Dit is precies de fout die we bij een vergelijkingssite hebben aangetroffen.
    if t1 is not None and t2 is not None and t1 > t2:
        errors.append(
            f"  - {key} ({name}): daltarief ({t1}) is hoger dan normaaltarief ({t2}) — onmogelijk, "
            f"waarschijnlijk zijn de velden verwisseld"
        )

    for field, band in (('elec_t1', ELEC_BAND), ('elec_t2', ELEC_BAND),
                        ('gas', GAS_BAND), ('return', RETURN_BAND)):
        value = fp.get(field)
        if value is not None and not _in_band(value, band):
            errors.append(
                f"  - {key} ({name}): fixed_prices.{field}={value} valt buiten de verwachte "
                f"bandbreedte {band[0]}-{band[1]} — controleer of dit een all-in tarief is"
            )

    # exit_fee=0.0 betekent 'geen opzegvergoeding'. Dat is een harde bewering; als die niet klopt
    # rekent een latere TCO-weergave zich rijk. null (= onbekend/variabel) is de veilige waarde.
    if info.get('exit_fee') == 0.0 and not info.get('exit_fee_note'):
        errors.append(
            f"  - {key} ({name}): exit_fee=0.0 zonder exit_fee_note. Als er wel een opzegvergoeding "
            f"is (of die variabel is), gebruik null + exit_fee_note."
        )

    return errors

def main():
    with open(PROVIDERS_FILE, 'r') as f:
        data = json.load(f)

    today = date.today()
    warnings = []
    errors = []

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
            errors.extend(check_fixed_plausibility(key, info))

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
        print(f"\n⚠️  {len(warnings)} waarschuwing(en) — verouderde tarieven (>{MAX_AGE_DAYS} dagen):")
        for w in warnings:
            print(w)
        print("\nActie gewenst: controleer de tarieven op de websites van deze aanbieders")
        print("en werk return_cost/return_verified of rate_verified bij in providers.json.\n")
        # Geen sys.exit(1) — oud is vervelend, niet fataal.
    else:
        print(f"✅ Alle tarieven zijn actueel (geverifieerd binnen {MAX_AGE_DAYS} dagen)")

    if errors:
        print(f"\n❌ {len(errors)} FOUT(EN) — onmogelijke of onvolledige tariefdata:")
        for e in errors:
            print(e)
        print("\nDeze data levert verkeerde bedragen op in de kostenvergelijking, waar een gebruiker")
        print("een meerjarig contract op baseert. Corrigeer dit voordat het naar de Pi's gaat.\n")
        sys.exit(1)

    print("✅ Plausibiliteitscontrole op vaste contracten geslaagd")

if __name__ == '__main__':
    main()
