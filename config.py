import os

from dotenv import load_dotenv



# Cargar las variables del archivo .env

load_dotenv()



# --- RECUPERAR SECRETOS ---

API_KEY = os.getenv('BINANCE_API_KEY')

SECRET_KEY = os.getenv('BINANCE_SECRET_KEY')



# Telegram

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')

TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')



# Server

HOST = os.getenv('HOST', '127.0.0.1') # Si no encuentra, usa default

PORT = int(os.getenv('PORT', 65432))



# --- VARIABLES PÚBLICAS (Esto sí puede ir en código) ---

CAPITAL_INICIAL = 20.0  # USDT

TIMEFRAME = '1m'
