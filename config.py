import os
from dotenv import load_dotenv

# Cargar las variables del archivo .env
load_dotenv()

# --- CREDENCIALES BINANCE ---
API_KEY = os.getenv('BINANCE_API_KEY')
SECRET_KEY = os.getenv('BINANCE_SECRET_KEY')

# --- SEGURIDAD INTERNA (NUEVO) ---
# Esta es la línea que faltaba. Carga el secreto y lo convierte a bytes.
EXECUTOR_SECRET = os.getenv('EXECUTOR_SECRET', 'default_inseguro').encode()

# --- CREDENCIALES TELEGRAM ---
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# --- CONFIGURACIÓN DEL SERVER ---
HOST = os.getenv('HOST', '127.0.0.1')
PORT = int(os.getenv('PORT', 65432))

# --- VARIABLES TRADING ---
CAPITAL_INICIAL = 20.0  # USDT
