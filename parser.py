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

FIREBASE_DB_URL = "https://pinnacle-tracker-a1f41-default-rtdb.firebaseio.com/" 

if not firebase_admin._apps:
    firebase_admin.initialize_app(cred, {
        'databaseURL': FIREBASE_DB_URL
    })

# 2. Конфигурация RapidAPI
RAPIDAPI_KEY = os.environ.get('RAPIDAPI_KEY')
RAPIDAPI_HOST = "pinnacle-odds-api.p.rapidapi.com"

headers = {
    "x-rapidapi-key": RAPIDAPI_KEY,
    "x-rapidapi-host": RAPIDAPI_HOST
}

def get_all_basketball_leagues():
    """Шаг 1: Получаем список всех живых лиг для баскетбола (sport_id = 4)"""
    url = "https://pinnacle-odds-api.p.rapidapi.com/4/leagues"
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            leagues = response.json()
            # Собираем только ID тех лиг, у которых есть активные матчи
            return [str(lg.get('id')) for lg in leagues if lg.get('has_documents') or lg.get('id')]
        else:
            print(f"Не удалось получить список лиг. Ошибка {response.status_code}")
            return []
    except Exception as e:
        print(f"Ошибка при запросе списка лиг: {e}")
        return []

def get_odds_for_league(league_id):
    """Шаг 2: Скачиваем матчи для конкретной лиги"""
    url = f"https://pinnacle-odds-api.p.rapidapi.com/odds/{league_id}"
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list):
                return data
            return data.get('events', [])
        return []
    except:
        return []

def save_to_firebase(events, current_time):
    """Шаг 3: Сохраняем матчи в Firebase"""
    ref = db.reference('basketball_lines')
    count = 0
    
    for event in events:
        periods = event.get('periods', {})
        num_0 = periods.get('num_0', {})
        moneyline = num_0.get('moneyline', {})
        
        if not moneyline:
            continue 
            
        event_id = str(event.get('id'))
        home_team = event.get('home', 'Home Team')
        away_team = event.get('away', 'Away Team')
        league = event.get('league_name', 'Basketball League')
        start_time = event.get('starts', '')
        
        home_odds = float(moneyline.get('home', 0))
        away_odds = float(moneyline.get('away', 0))
        
        if home_odds == 0 or away_odds == 0:
            continue

        history_entry = {
            "timestamp": current_time,
            "home_odds": home_odds,
            "away_odds": away_odds
        }
        
        match_ref = ref.child(event_id)
        match_ref.child('info').update({
            "home": home_team,
            "away": away_team,
            "league": league,
            "starts": start_time,
            "last_home_odds": home_odds,
            "last_away_odds": away_odds,
            "last_update": current_time
        })
        match_ref.child('history').push(history_entry)
        count += 1
    return count

if __name__ == "__main__":
    print("Начинаем сбор всех баскетбольных лиг...")
    league_ids = get_all_basketball_leagues()
    
    if not league_ids:
        print("Активные лиги не найдены. Проверь подписку или RAPIDAPI_KEY.")
    else:
        print(f"Найдено лиг для проверки: {len(league_ids)}. Начинаем сбор коэффициентов...")
        total_saved = 0
        current_time = int(time.time())
        
        # Перебираем лиги по очереди (берем первые 20, чтобы не превысить лимиты за один запуск)
        for idx, league_id in enumerate(league_ids[:20]):
            events = get_odds_for_league(league_id)
            if events:
                saved = save_to_firebase(events, current_time)
                total_saved += saved
            # Небольшая пауза, чтобы RapidAPI не ругался на спам-запросы
            time.sleep(0.5)
            
        print(f"Сбор завершен! Всего добавлено матчей из всех лиг в Firebase: {total_saved}")
