import ccxt
import time
import json
import socket
import config

# --- CONFIGURACION ---
MIN_PROFIT_NETO = 0.2  # Target minimo de profit %
FEE_ESTIMADO = 0.35    # Fees exchange + Slippage buffer

print("System: Iniciando Scanner de Arbitraje...")

# Init exchange (Solo lectura)
exchange = ccxt.binance({
    'apiKey': config.API_KEY,
    'secret': config.SECRET_KEY,
    'enableRateLimit': True
})

def enviar_al_executor(ruta):
    """Dispatch de señal al socket del executor"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((config.HOST, config.PORT))
        
        payload = {
            "ruta": ruta,
            "timestamp": time.time()
        }
        
        s.send(json.dumps(payload).encode())
        s.close()
        print(f">> Signal enviada: {ruta}")
        return True
    except Exception as e:
        print(f"Error socket: {e}")
        return False

def obtener_precios_masivos():
    """Fetch de todos los tickers"""
    try:
        return exchange.fetch_tickers()
    except Exception as e:
        print(f"Error fetch tickers: {e}")
        return {}

def buscar_oportunidades():
    # Load markets y tickers
    mercados = exchange.load_markets()
    tickers = obtener_precios_masivos()
    
    # Filtrar pares base USDT activos
    pares_usdt = [s for s in mercados if '/USDT' in s and mercados[s]['active']]
    
    print(f"Analizando {len(pares_usdt)} activos...")

    for par_1 in pares_usdt:
        moneda_intermedia = par_1.split('/')[0]
        
        # Skip tokens apalancados (UP/DOWN)
        if 'UP/' in par_1 or 'DOWN/' in par_1:
            continue

        # Definicion de rutas triangulares (Hardcoded para ETH, BNB, BTC)
        rutas_posibles = [
            {'ruta': [par_1, f"{moneda_intermedia}/ETH", "ETH/USDT"], 'tipo': 'ETH'},
            {'ruta': [par_1, f"{moneda_intermedia}/BNB", "BNB/USDT"], 'tipo': 'BNB'},
            {'ruta': [par_1, f"{moneda_intermedia}/BTC", "BTC/USDT"], 'tipo': 'BTC'}
        ]

        for op in rutas_posibles:
            ruta = op['ruta']
            
            # Validar que los 3 pares existan en el dict de tickers
            if all(par in tickers for par in ruta):
                p1 = tickers[ruta[0]]['ask']
                p3 = tickers[ruta[2]]['bid']
                
                # Simulacion con capital base 100
                inicio = 100.0
                
                # Step 1: USDT -> A
                step1 = inicio / p1
                
                # Step 2: A -> B (Validacion de side bid/ask)
                try:
                    # Determinar si vendemos o compramos segun la base del par intermedio
                    if mercados[ruta[1]]['base'] == moneda_intermedia:
                        step2 = step1 * tickers[ruta[1]]['bid'] # Sell
                    else:
                        step2 = step1 / tickers[ruta[1]]['ask'] # Buy
                except:
                    continue 

                # Step 3: B -> USDT
                final = step2 * p3
                
                # Calculo de ROI
                roi_bruto = ((final - inicio) / inicio) * 100
                roi_neto = roi_bruto - FEE_ESTIMADO
                
                # Trigger si supera el umbral
                if roi_neto > MIN_PROFIT_NETO:
                    print(f"MATCH: {ruta} | Bruto: {roi_bruto:.2f}% | Neto: {roi_neto:.2f}%")
                    
                    enviar_al_executor(ruta)
                    
                    # Cooldown para evitar spam de signals
                    time.sleep(10)

    print("Scan completado. Idle 2s...")
    time.sleep(2)

if __name__ == "__main__":
    while True:
        try:
            buscar_oportunidades()
        except KeyboardInterrupt:
            print("Deteniendo proceso...")
            break
        except Exception as e:
            print(f"Exception main loop: {e}")
            time.sleep(5)
