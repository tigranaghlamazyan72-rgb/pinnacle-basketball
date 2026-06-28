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
    # Смотрим все активные баскетбольные лиги
    url = "https://api.the-odds-api.com/v4/sports/"
    params = {"apiKey": API_KEY}
    
    response = requests.get(url, params=params, timeout=15)
    sports = response.json()
    
    basketball = [s for s in sports if 'basketball' in s['key'] and s['active']]
    print("=== Активные баскетбольные лиги ===")
    for s in basketball:
        print(f"{s['key']} — {s['title']}")
    
    return []  # пока просто смотрим список

if __name__ == "__main__":
    if not API_KEY:
        print("Ошибка: THEODDSAPI_KEY не задан")
    else:
        data = get_basketball_odds()
