import os
import requests
import time
import json
import firebase_admin
from firebase_admin import credentials
from firebase_admin import db

# 1. Инициализация базы данных Firebase
# Скрипт ищет ключ локально, а если его нет (на GitHub) — берет из настроек облака
if os.path.exists('serviceAccountKey.json'):
    cred = credentials.Certificate('serviceAccountKey.json')
else:
    firebase_creds = json.loads(os.environ.get('FIREBASE_CONFIG_JSON'))
    cred = credentials.Certificate(firebase_creds)

# !!! СЮДА ВСТАВЬ ССЫЛКУ НА СВОЮ БАЗУ ИЗ FIREBASE (ЗАКАНЧИВАЕТСЯ НА .firebaseio.com/) !!!
FIREBASE_DB_URL = "https://pinnacle-tracker-a1f41-default-rtdb.firebaseio.com/" 

if not firebase_admin._apps:
    firebase_admin.initialize_app(cred, {
        'databaseURL': FIREBASE_DB_URL
    })

# 2. Конфигурация запроса к API Pinnacle через RapidAPI
RAPIDAPI_KEY = os.environ.get('RAPIDAPI_KEY', 'ЗДЕСЬ_МОЖЕТ_БЫТЬ_ТВОЙ_КЛЮЧ_ДЛЯ_ТЕСТОВ_ДОМА')
RAPIDAPI_HOST = "pinnacle-odds.p.rapidapi.com"

def get_basketball_lines():
    url = "https://pinnacle-odds.p.rapidapi.com/kit/v1/markets"
    # sport_id: 4 означает баскетбол, по умолчанию берем прематч (is_live: false)
    querystring = {"sport_id": "4", "is_live": "false"}
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST
    }
    
    try:
        response = requests.get(url, headers=headers, params=querystring, timeout=10)
        if response.status_code == 200:
            return response.json().get('events', [])
        else:
            print(f"Ошибка API: {response.status_code}")
            return []
    except Exception as e:
        print(f"Ошибка запроса: {e}")
        return []

def save_to_firebase(events):
    ref = db.reference('basketball_lines')
    current_time = int(time.time())
    
    for event in events:
        periods = event.get('periods', {})
        num_0 = periods.get('num_0', {}) # Линия на весь матч
        moneyline = num_0.get('moneyline', {})
        
        if not moneyline:
            continue 
            
        event_id = str(event.get('id'))
        home_team = event.get('home')
        away_team = event.get('away')
        league = event.get('league_name')
        start_time = event.get('starts')
        
        home_odds = moneyline.get('home')
        away_odds = moneyline.get('away')
        
        # Данные для истории
        history_entry = {
            "timestamp": current_time,
            "home_odds": home_odds,
            "away_odds": away_odds
        }
        
        match_ref = ref.child(event_id)
        
        # Сохраняем текущие кэфы
        match_ref.child('info').update({
            "home": home_team,
            "away": away_team,
            "league": league,
            "starts": start_time,
            "last_home_odds": home_odds,
            "last_away_odds": away_odds,
            "last_update": current_time
        })
        
        # Дописываем кэфы в историю изменений
        match_ref.child('history').push(history_entry)
        
    print(f"База данных успешно обновлена! Найдено матчей: {len(events)}")

if __name__ == "__main__":
    lines = get_basketball_lines()
    if lines:
        save_to_firebase(lines)