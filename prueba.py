import socket
import json
from config import HOST, PORT

# Datos falsos para ver si llega el mensaje
fake_data = {
    "ruta": ["USDT/TEST", "FAKE/TEST", "FAKE/USDT"],
    "precios": [1.0, 1.0, 1.0]
}

try:
    print(f"📡 Llamando a la puerta {HOST}:{PORT}...")
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((HOST, PORT))
    s.send(json.dumps(fake_data).encode())
    s.close()
    print("✅ ¡Timbre tocado! Mensaje enviado correctamente.")
except ConnectionRefusedError:
    print("❌ NADIE CONTESTA. El Executor está apagado o en otro puerto.")
except Exception as e:
    print(f"❌ Error raro: {e}")

