import os
import requests
import time
import json
import firebase_admin
from firebase_admin import credentials, db

if os.path.exists('serviceAccountKey.json'):
    cred = credentials.Certificate('serviceAccountKey.json')
else:
    cred = credentials.Certificate(json.loads(os.environ.get('FIREBASE_CONFIG_JSON')))

FIREBASE_DB_URL = "https://pinnacle-tracker-a1f41-default-rtdb.firebaseio.com/"
if not firebase_admin._apps:
    firebase_admin.initialize_app(cred, {'databaseURL': FIREBASE_DB_URL})

API_KEY = os.environ.get('THEODDSAPI_KEY')

def get_basketball_odds():
    # NBA — sport key: basketball_nba
    # Евролига: basketball_euroleague
    # NCB: basketball_ncaab
    sport = "basketball_nba"
    
    url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds/"
    params = {
        "apiKey": API_KEY,
        "regions": "eu",           # европейские букмекеры (включая Pinnacle)
        "markets": "h2h",          # moneyline = h2h
        "bookmakers": "pinnacle",
        "oddsFormat": "decimal"
    }

    try:
        response = requests.get(url, params=params, timeout=15)
        print(f"HTTP статус: {response.status_code}")
        remaining = response.headers.get('x-requests-remaining', '?')
        print(f"Остаток запросов: {remaining}")

        if response.status_code == 200:
            data = response.json()
            print(f"Матчей получено: {len(data)}")
            if data:
                print("Структура первого матча:")
                print(json.dumps(data[0], indent=2, ensure_ascii=False))
            return data
        else:
            print(f"Ошибка: {response.status_code} — {response.text}")
            return []
    except Exception as e:
        print(f"Исключение: {e}")
        return []

def save_to_firebase(fixtures):
    ref = db.reference('basketball_lines')
    current_time = int(time.time())
    count = 0

    for fixture in fixtures:
        # Ищем Pinnacle среди букмекеров
        pinnacle = next((b for b in fixture.get('bookmakers', []) if b['key'] == 'pinnacle'), None)
        if not pinnacle:
            continue

        # Ищем рынок h2h
        h2h = next((m for m in pinnacle.get('markets', []) if m['key'] == 'h2h'), None)
        if not h2h:
            continue

        outcomes = {o['name']: o['price'] for o in h2h.get('outcomes', [])}
        home_team = fixture['home_team']
        away_team = fixture['away_team']
        home_odds = outcomes.get(home_team, 0)
        away_odds = outcomes.get(away_team, 0)

        if not home_odds or not away_odds:
            continue

        event_id = fixture['id']

        match_ref = ref.child(event_id)
        match_ref.child('info').update({
            "home": home_team,
            "away": away_team,
            "league": fixture.get('sport_title', 'Basketball'),
            "starts": fixture.get('commence_time', ''),
            "last_home_odds": home_odds,
            "last_away_odds": away_odds,
            "last_update": current_time,
            "bookmaker_source": "Pinnacle"
        })
        match_ref.child('history').push({
            "timestamp": current_time,
            "home_odds": home_odds,
            "away_odds": away_odds
        })
        count += 1

    print(f"Обновлено матчей: {count}")

if __name__ == "__main__":
    if not API_KEY:
        print("Ошибка: THEODDSAPI_KEY не задан")
    else:
        data = get_basketball_odds()
        if data:
            save_to_firebase(data)
        else:
            print("Данные не получены")
