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

# 2. Конфигурация OddsPapi
# Скрипт возьмет ключ из твоего секрет-поля RAPIDAPI_KEY на GitHub
API_KEY = os.environ.get('RAPIDAPI_KEY')
API_HOST = "oddspapi.p.rapidapi.com" # Хост для RapidAPI шлюза

def get_basketball_odds_from_papi():
    url = "https://oddspapi.p.rapidapi.com/v5/odds"
    
    params = {
        "sport": "basketball",
        "bookmakers": "pinnacle",
        "markets": "moneyline"
    }
    
    headers = {
        "x-rapidapi-key": API_KEY,
        "x-rapidapi-host": API_HOST
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)
        print(f"=== HTTP статус: {response.status_code} ===")
        print(f"=== Ответ от API (первые 2000 символов) ===")
        print(response.text[:2000])
        
        if response.status_code == 200:
            res_data = response.json()
            print(f"=== Тип ответа: {type(res_data)} ===")
            if isinstance(res_data, list):
                print(f"=== Количество матчей: {len(res_data)} ===")
                if res_data:
                    print("=== Структура первого матча ===")
                    print(json.dumps(res_data[0], indent=2, ensure_ascii=False))
                return res_data
            else:
                print(f"=== Ключи верхнего уровня: {list(res_data.keys())} ===")
                result = res_data.get('data', res_data.get('results', []))
                print(f"=== Найдено матчей: {len(result)} ===")
                return result
        else:
            print(f"Ошибка OddsPapi: {response.status_code}")
            print(f"Ответ: {response.text}")
            return []
    except Exception as e:
        print(f"Ошибка запроса: {e}")
        return []

def save_to_firebase(fixtures):
    ref = db.reference('basketball_lines')
    current_time = int(time.time())
    count = 0
    
    for fixture in fixtures:
        # Парсим структуру матча согласно нормализованному формату OddsPapi
        # Обычно: fixture['home_team'], fixture['away_team'], fixture['odds']
        home_team = fixture.get('home_team', fixture.get('home'))
        away_team = fixture.get('away_team', fixture.get('away'))
        league = fixture.get('tournament_name', fixture.get('league', 'Basketball Match'))
        start_time = fixture.get('start_time', fixture.get('starts', ''))
        
        # Вытаскиваем коэффициенты букмекера
        odds_data = fixture.get('odds', {})
        pinnacle_odds = odds_data.get('pinnacle', {})
        
        # Если вложенность глубже (например, через маркет h2h/moneyline)
        if not pinnacle_odds and 'moneyline' in odds_data:
            pinnacle_odds = odds_data.get('moneyline', {}).get('pinnacle', {})
            
        if not pinnacle_odds:
            continue # Пропускаем матч, если Пинакл еще не дал на него линию
            
        # Названия ключей кэфов обычно 'home'/'away' или '1'/'2'
        home_odds = float(pinnacle_odds.get('home', pinnacle_odds.get('1', 0)))
        away_odds = float(pinnacle_odds.get('away', pinnacle_odds.get('2', 0)))
        
        if home_odds == 0 or away_odds == 0:
            continue

        event_id = str(fixture.get('id', fixture.get('fixture_id', count)))
        
        history_entry = {
            "timestamp": current_time,
            "home_odds": home_odds,
            "away_odds": away_odds
        }
        
        match_ref = ref.child(event_id)
        
        # Записываем актуальную инфу
        match_ref.child('info').update({
            "home": home_team,
            "away": away_team,
            "league": league,
            "starts": start_time,
            "last_home_odds": home_odds,
            "last_away_odds": away_odds,
            "last_update": current_time,
            "bookmaker_source": "Pinnacle"
        })
        
        # Пушим точку в историю изменений
        match_ref.child('history').push(history_entry)
        count += 1
        
    print(f"Синхронизация с OddsPapi завершена! Обновлено матчей: {count}")

if __name__ == "__main__":
    if not API_KEY:
        print("Критическая ошибка: RAPIDAPI_KEY не задан в Secrets на GitHub.")
    else:
        data = get_basketball_odds_from_papi()
        if data:
            save_to_firebase(data)
        else:
            print("Линия OddsPapi пуста или эндпоинт вернул пустой массив.")
