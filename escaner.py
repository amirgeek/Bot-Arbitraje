import ccxt
import time
import json
import socket
import hmac
import hashlib
import config

# --- SETTINGS PRO ---
MIN_PROFIT_NETO = 0.20  # Ganancia mínima limpia
INVERSION_SIMULADA = 15.0 # Simulamos con el capital real ($15) para ver el impacto en el libro
FEE_EXCHANGE = 0.001    # 0.1% Binance Fee (Nivel Base)

print("🔎 ESCÁNER v3.0: Análisis de Profundidad (Slippage) Activado...")

exchange = ccxt.binance({
    'apiKey': config.API_KEY,
    'secret': config.SECRET_KEY,
    'enableRateLimit': True
})

def obtener_precio_profundidad(symbol, side, cantidad_requerida):
    """
    Descarga el Order Book y calcula el precio promedio REAL
    que pagaríamos por esa cantidad (Slippage).
    """
    try:
        # Descargamos las mejores 20 órdenes del libro
        book = exchange.fetch_order_book(symbol, limit=20)
        
        # Si queremos COMPRAR (Buy), miramos los ASKS (Vendedores)
        # Si queremos VENDER (Sell), miramos los BIDS (Compradores)
        ordenes = book['asks'] if side == 'buy' else book['bids']
        
        cantidad_acumulada = 0
        costo_acumulado = 0
        
        for precio, volumen in ordenes:
            # Cuánto tomamos de esta orden
            tomar = min(volumen, cantidad_requerida - cantidad_acumulada)
            
            costo_acumulado += tomar * precio
            cantidad_acumulada += tomar
            
            if cantidad_acumulada >= cantidad_requerida:
                break
        
        if cantidad_acumulada < cantidad_requerida:
            return None # No hay suficiente liquidez en el libro top 20
            
        precio_promedio = costo_acumulado / cantidad_acumulada
        return precio_promedio

    except Exception as e:
        # print(f"Error libro {symbol}: {e}")
        return None

def enviar_al_executor(ruta):
    try:
        payload = {"ruta": ruta, "timestamp": time.time(), "version": "1.0"}
        data_str = json.dumps(payload)
        firma = hmac.new(config.EXECUTOR_SECRET, data_str.encode(), hashlib.sha256).hexdigest()
        msg = (json.dumps({"data": data_str, "signature": firma}) + "\n").encode()
        
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)
        s.connect((config.HOST, config.PORT))
        s.sendall(msg)
        s.close()
        print(f"✅ Oportunidad VALIDADA y ENVIADA: {ruta}")
        return True
    except: return False

def buscar_oportunidades():
    mercados = exchange.load_markets()
    tickers = exchange.fetch_tickers() # Barrido rápido inicial
    
    pares_usdt = [s for s in mercados if '/USDT' in s and mercados[s]['active']]
    print(f"📡 Escaneando {len(pares_usdt)} mercados...")

    for par_1 in pares_usdt:
        coin = par_1.split('/')[0]
        if 'UP/' in par_1 or 'DOWN/' in par_1: continue

        # Definimos rutas (solo triangulares clásicas líquidas)
        rutas = [
            {'ruta': [par_1, f"{coin}/ETH", "ETH/USDT"], 'intermedio': 'ETH'},
            {'ruta': [par_1, f"{coin}/BTC", "BTC/USDT"], 'intermedio': 'BTC'},
            {'ruta': [par_1, f"{coin}/BNB", "BNB/USDT"], 'intermedio': 'BNB'}
        ]

        for op in rutas:
            ruta = op['ruta']
            # Filtro 1: Existencia
            if not all(k in tickers for k in ruta): continue

            # --- FASE 1: CÁLCULO RÁPIDO (PRE-FILTRO) ---
            # Usamos tickers simples para ver si "pintar" ganancia
            try:
                p1 = tickers[ruta[0]]['ask']
                p3 = tickers[ruta[2]]['bid']
                
                # Check dirección paso 2
                base_p2 = mercados[ruta[1]]['base']
                if base_p2 == coin: # Sell A -> B
                    p2_raw = tickers[ruta[1]]['bid']
                    factor_p2 = p2_raw
                else: # Buy B -> A (Inverso)
                    p2_raw = tickers[ruta[1]]['ask']
                    factor_p2 = 1/p2_raw

                # Simulación rápida
                res_fast = (100 / p1) * factor_p2 * p3
                roi_fast = res_fast - 100
                
                # Si no da al menos 0.5% en bruto, ni nos molestamos en mirar el libro
                if roi_fast < 0.5: continue 

            except: continue

            # --- FASE 2: CÁLCULO REAL (PROFUNDIDAD / SLIPPAGE) ---
            print(f"🧐 Analizando profundidad para {ruta} (ROI Est: {roi_fast:.2f}%)")
            
            capital = INVERSION_SIMULADA
            
            # Paso 1: USDT -> A (Buy)
            precio_real_1 = obtener_precio_profundidad(ruta[0], 'buy', capital/tickers[ruta[0]]['ask'])
            if not precio_real_1: continue
            
            cant_a = (capital / precio_real_1) * (1 - FEE_EXCHANGE)
            
            # Paso 2: A -> B
            base_p2 = mercados[ruta[1]]['base']
            if base_p2 == coin: # Sell A (tenemos Coin)
                precio_real_2 = obtener_precio_profundidad(ruta[1], 'sell', cant_a)
                if not precio_real_2: continue
                cant_b = (cant_a * precio_real_2) * (1 - FEE_EXCHANGE)
            else: # Buy A (tenemos B? No, queremos comprar B con A... wait.
                  # Ruta: USDT->Coin->ETH. Par Coin/ETH. Base=Coin. Sell Coin. Correcto.
                  # Ruta: USDT->ETH->Coin. Par ETH/Coin. Base=ETH. Buy Coin? No, Sell ETH.
                  # Simplificamos: Asumimos par A/Intermedio siempre es Sell A.
                  # Si el par es Intermedio/A, es Buy Intermedio con A.
                  # Lógica de conversión precisa:
                  if base_p2 == op['intermedio']: # Par es ETH/Coin. Tenemos Coin. Queremos ETH.
                      # Es "Buy ETH con Coin". En Spot es vender Coin por ETH? No existe.
                      # Spot es Base/Quote. Si par es ETH/Coin, compramos ETH pagando Coin.
                      # Quote es Coin. Side = Buy.
                      precio_real_2 = obtener_precio_profundidad(ruta[1], 'buy', cant_a) # Cantidad es estimativa en base
                      if not precio_real_2: continue
                      # Cantidad B (ETH) = Cantidad A (Coin) / Precio
                      cant_b = (cant_a / precio_real_2) * (1 - FEE_EXCHANGE)
                  else: 
                      # Par es Coin/ETH. Tenemos Coin. Vendemos Coin.
                      precio_real_2 = obtener_precio_profundidad(ruta[1], 'sell', cant_a)
                      if not precio_real_2: continue
                      cant_b = (cant_a * precio_real_2) * (1 - FEE_EXCHANGE)

            # Paso 3: B -> USDT (Sell)
            precio_real_3 = obtener_precio_profundidad(ruta[2], 'sell', cant_b)
            if not precio_real_3: continue
            
            final_usdt = (cant_b * precio_real_3) * (1 - FEE_EXCHANGE)
            
            # RESULTADO FINAL NETO
            profit_neto = final_usdt - capital
            profit_pct = (profit_neto / capital) * 100
            
            if profit_pct > MIN_PROFIT_NETO:
                print(f"💎 GEM ENCONTRADA: {ruta}")
                print(f"   Inversión: ${capital} -> Retorno: ${final_usdt:.2f}")
                print(f"   Profit Neto (tras fees y slippage): {profit_pct:.2f}%")
                
                enviar_al_executor(ruta)
                time.sleep(15) # Pausa larga para ejecutar

    time.sleep(1)

if __name__ == "__main__":
    while True:
        try: buscar_oportunidades()
        except KeyboardInterrupt: break
        except Exception as e: 
            print(f"Error loop: {e}")
            time.sleep(5)
