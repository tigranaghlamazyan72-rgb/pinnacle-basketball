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

def get_active_basketball_sports():
    url = "https://api.the-odds-api.com/v4/sports/"
    params = {"apiKey": API_KEY}
    response = requests.get(url, params=params, timeout=15)
    sports = response.json()
    # Этот запрос НЕ тратит квоту
    return [s['key'] for s in sports if 'basketball' in s['key'] and s['active']]

def get_odds_for_sport(sport_key):
    url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds/"
    params = {
        "apiKey": API_KEY,
        "regions": "eu",
        "markets": "h2h",
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

def save_to_firebase(fixtures, sport_key):
    ref = db.reference('basketball_lines')
    current_time = int(time.time())
    count = 0

    for fixture in fixtures:
        pinnacle = next((b for b in fixture.get('bookmakers', []) if b['key'] == 'pinnacle'), None)
        if not pinnacle:
            continue

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

        # Проверяем предыдущие коэффициенты
        existing = match_ref.child('info').get()
        if existing:
            prev_home = existing.get('last_home_odds', 0)
            prev_away = existing.get('last_away_odds', 0)
            home_changed = abs(home_odds - prev_home) >= 0.01
            away_changed = abs(away_odds - prev_away) >= 0.01
            
            if home_changed or away_changed:
                print(f"⚡ ДВИЖЕНИЕ: {home_team} vs {away_team}")
                if home_changed:
                    print(f"   П1: {prev_home:.2f} → {home_odds:.2f}")
                if away_changed:
                    print(f"   П2: {prev_away:.2f} → {away_odds:.2f}")
            else:
                # Коэффициенты не изменились — историю не пишем
                continue

        match_ref.child('info').update({
            "home": home_team,
            "away": away_team,
            "league": fixture.get('sport_title', sport_key),
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

    return count

if __name__ == "__main__":
    if not API_KEY:
        print("Ошибка: THEODDSAPI_KEY не задан")
    else:
        sports = get_active_basketball_sports()
        print(f"Активных баскетбольных лиг: {len(sports)} — {sports}")
        
        total = 0
        for sport_key in sports:
            fixtures = get_odds_for_sport(sport_key)
            if fixtures:
                updated = save_to_firebase(fixtures, sport_key)
                total += updated
        
        print(f"Итого обновлено матчей с движением: {total}")
