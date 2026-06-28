import os
import requests
import time
import json
import firebase_admin
from firebase_admin import credentials
from firebase_admin import db

# 1. Инициализация базы данных Firebase
if os.path.exists('serviceAccountKey.json'):
    cred = credentials.Certificate('serviceAccountKey.json')
else:
    firebase_creds = json.loads(os.environ.get('FIREBASE_CONFIG_JSON'))
    cred = credentials.Certificate(firebase_creds)

# ТВОЙ URL ИЗ ФАЙРБЕЙС
FIREBASE_DB_URL = "https://pinnacle-tracker-a1f41-default-rtdb.firebaseio.com/" 

if not firebase_admin._apps:
    firebase_admin.initialize_app(cred, {
        'databaseURL': FIREBASE_DB_URL
    })

# 2. Конфигурация запроса к API Pinnacle через RapidAPI
RAPIDAPI_KEY = os.environ.get('RAPIDAPI_KEY')
RAPIDAPI_HOST = "pinnacle-odds-api.p.rapidapi.com"

def get_basketball_lines():
    # Запрашиваем ВСЕ прематч коэффициенты (v2/odds). sport_id=4 — это баскетбол.
    url = "https://pinnacle-odds-api.p.rapidapi.com/pinnacle/v2/odds"
    
    querystring = {"sport_id": "4", "page": "1", "perPage": "30"}
    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": RAPIDAPI_HOST
    }
    
    try:
        response = requests.get(url, headers=headers, params=querystring, timeout=15)
        if response.status_code == 200:
            # API возвращает объект, где матчи лежат в ключе 'events'
            return response.json().get('events', [])
        else:
            print(f"Ошибка API: {response.status_code}")
            print(f"Ответ сервера: {response.text}")
            return []
    except Exception as e:
        print(f"Ошибка запроса: {e}")
        return []

def save_to_firebase(events):
    ref = db.reference('basketball_lines')
    current_time = int(time.time())
    count = 0
    
    for event in events:
        periods = event.get('periods', {})
        num_0 = periods.get('num_0', {}) # Линия на матч целиком
        moneyline = num_0.get('moneyline', {})
        
        # Если кэфов на П1/П2 нет, пропускаем матч
        if not moneyline:
            continue 
            
        event_id = str(event.get('id'))
        home_team = event.get('home')
        away_team = event.get('away')
        league = event.get('league_name', 'Basketball League')
        start_time = event.get('starts')
        
        home_odds = float(moneyline.get('home'))
        away_odds = float(moneyline.get('away'))
        
        history_entry = {
            "timestamp": current_time,
            "home_odds": home_odds,
            "away_odds": away_odds
        }
        
        match_ref = ref.child(event_id)
        
        # Обновляем инфо
        match_ref.child('info').update({
            "home": home_team,
            "away": away_team,
            "league": league,
            "starts": start_time,
            "last_home_odds": home_odds,
            "last_away_odds": away_odds,
            "last_update": current_time
        })
        
        # Записываем шаг в историю
        match_ref.child('history').push(history_entry)
        count += 1
        
    print(f"База данных успешно обновлена! Записано матчей: {count}")

if __name__ == "__main__":
    lines = get_basketball_lines()
    if lines:
        save_to_firebase(lines)
    else:
        print("Линия пуста. Проверь подписку на тариф в RapidAPI.")
