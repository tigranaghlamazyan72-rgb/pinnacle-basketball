import os
import requests
import time
import json
import firebase_admin
from firebase_admin import credentials, db

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

def send_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "HTML"
            },
            timeout=10
        )
    except Exception as e:
        print(f"Telegram ошибка: {e}")

if os.path.exists('serviceAccountKey.json'):
    cred = credentials.Certificate('serviceAccountKey.json')
else:
    cred = credentials.Certificate(json.loads(os.environ.get('FIREBASE_CONFIG_JSON')))

FIREBASE_DB_URL = "https://pinnacle-tracker-a1f41-default-rtdb.firebaseio.com/"
if not firebase_admin._apps:
    firebase_admin.initialize_app(cred, {'databaseURL': FIREBASE_DB_URL})

API_KEY = os.environ.get('THEODDSAPI_KEY')

def get_active_basketball_sports():
    url = "https://api.the-odds-api.com/v4/sports/"
    params = {"apiKey": API_KEY}
    response = requests.get(url, params=params, timeout=15)
    sports = response.json()
    result = [s['key'] for s in sports if 'basketball' in s['key'] and s['active']]
    print(f"Активные баскетбольные лиги: {result}")
    return result

def get_odds_for_sport(sport_key):
    url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds/"
    params = {
        "apiKey": API_KEY,
        "regions": "eu",
        "markets": "spreads,totals",
        "bookmakers": "pinnacle",
        "oddsFormat": "decimal"
    }
    try:
        response = requests.get(url, params=params, timeout=15)
        remaining = response.headers.get('x-requests-remaining', '?')
        print(f"[{sport_key}] статус: {response.status_code} | остаток запросов: {remaining}")
        if response.status_code == 200:
            data = response.json()
            print(f"[{sport_key}] матчей: {len(data)}")
            return data
        else:
            print(f"[{sport_key}] ошибка: {response.text}")
            return []
    except Exception as e:
        print(f"[{sport_key}] исключение: {e}")
        return []

def parse_pinnacle_markets(fixture):
    pinnacle = next((b for b in fixture.get('bookmakers', []) if b['key'] == 'pinnacle'), None)
    if not pinnacle:
        return None

    result = {}

    for market in pinnacle.get('markets', []):
        key = market['key']
        outcomes = market.get('outcomes', [])

        if key == 'spreads':
            for o in outcomes:
                if o['name'] == fixture['home_team']:
                    result['home_spread'] = o.get('point', 0)
                    result['home_spread_odds'] = o.get('price', 0)
                elif o['name'] == fixture['away_team']:
                    result['away_spread'] = o.get('point', 0)
                    result['away_spread_odds'] = o.get('price', 0)

        elif key == 'totals':
            for o in outcomes:
                if o['name'] == 'Over':
                    result['total_line'] = o.get('point', 0)
                    result['over_odds'] = o.get('price', 0)
                elif o['name'] == 'Under':
                    result['under_odds'] = o.get('price', 0)

    return result if result else None

def save_to_firebase(fixtures, sport_key):
    ref = db.reference('basketball_lines')
    current_time = int(time.time())
    count = 0

    for fixture in fixtures:
        markets = parse_pinnacle_markets(fixture)
        if not markets:
            continue

        home_team = fixture['home_team']
        away_team = fixture['away_team']
        event_id = fixture['id']
        match_ref = ref.child(event_id)

        existing = match_ref.child('info').get()
        changed = False

        if existing:
            prev_spread = existing.get('home_spread', 0)
            prev_total = existing.get('total_line', 0)
            prev_over = existing.get('over_odds', 0)
            prev_under = existing.get('under_odds', 0)

            spread_changed = abs(markets.get('home_spread', 0) - prev_spread) >= 0.25
            total_changed = abs(markets.get('total_line', 0) - prev_total) >= 0.5
            odds_changed = (
                abs(markets.get('over_odds', 0) - prev_over) >= 0.01 or
                abs(markets.get('under_odds', 0) - prev_under) >= 0.01
            )

            if spread_changed or total_changed or odds_changed:
                changed = True
                lines = [f"⚡ <b>{home_team} vs {away_team}</b>"]
                lines.append(f"🏀 {fixture.get('sport_title', sport_key)}")
                if spread_changed:
                    lines.append(f"Фора: {prev_spread:+.1f} → {markets.get('home_spread'):+.1f}")
                if total_changed:
                    lines.append(f"Тотал: {prev_total} → {markets.get('total_line')}")
                if odds_changed:
                    lines.append(f"Over: {prev_over:.2f} → {markets.get('over_odds'):.2f} | Under: {prev_under:.2f} → {markets.get('under_odds'):.2f}")
                msg = "\n".join(lines)
                print(msg)
                send_telegram(msg)
            else:
                continue
        else:
            changed = True

        if changed:
            match_ref.child('info').update({
                "home": home_team,
                "away": away_team,
                "league": fixture.get('sport_title', sport_key),
                "starts": fixture.get('commence_time', ''),
                "home_spread": markets.get('home_spread', 0),
                "home_spread_odds": markets.get('home_spread_odds', 0),
                "away_spread": markets.get('away_spread', 0),
                "away_spread_odds": markets.get('away_spread_odds', 0),
                "total_line": markets.get('total_line', 0),
                "over_odds": markets.get('over_odds', 0),
                "under_odds": markets.get('under_odds', 0),
                "last_update": current_time,
                "bookmaker_source": "Pinnacle"
            })
            match_ref.child('history').push({
                "timestamp": current_time,
                **markets
            })
            count += 1

    return count

if __name__ == "__main__":
    if not API_KEY:
        print("Ошибка: THEODDSAPI_KEY не задан")
    else:
        sports = get_active_basketball_sports()
        total = 0
        for sport_key in sports:
            fixtures = get_odds_for_sport(sport_key)
            if fixtures:
                updated = save_to_firebase(fixtures, sport_key)
                total += updated
        print(f"Итого обновлено матчей с движением: {total}")
