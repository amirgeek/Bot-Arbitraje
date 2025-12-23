import asyncio
import json
import hmac
import hashlib
import ccxt.async_support as ccxt
from config import API_KEY, SECRET_KEY, CAPITAL_INICIAL, HOST, PORT, EXECUTOR_SECRET

# --- SETTINGS ---
TIMEOUT_ORDEN = 5      
MONEDA_BASE = 'USDT'   

exchange = ccxt.binance({
    'apiKey': API_KEY,
    'secret': SECRET_KEY,
    'options': {
        'defaultType': 'spot',
        'adjustForTimeDifference': True,
        'recvWindow': 10000 
    }
})

async def validar_firma(mensaje_json):
    """Valida que la orden venga del Escáner autorizado"""
    try:
        data_str = mensaje_json.get('data')
        firma_recibida = mensaje_json.get('signature')
        if not data_str or not firma_recibida: return False, None
        firma_calculada = hmac.new(EXECUTOR_SECRET, data_str.encode(), hashlib.sha256).hexdigest()
        if hmac.compare_digest(firma_recibida, firma_calculada):
            return True, json.loads(data_str)
        return False, None
    except: return False, None

async def ejecutar_orden_mercado(symbol, side, cantidad):
    """Ejecuta orden MARKET con TIMEOUT y retorno detallado"""
    try:
        print(f"⚡ {side.upper()} {symbol} Qty:{cantidad:.6f}...")
        qty_precisa = exchange.amount_to_precision(symbol, cantidad)
        
        orden = await asyncio.wait_for(
            exchange.create_order(symbol, 'market', side, qty_precisa),
            timeout=TIMEOUT_ORDEN
        )
        
        if orden['status'] == 'closed' or orden['filled'] > 0:
            filled = float(orden['filled'])
            cost = float(orden['cost']) if orden['cost'] else 0.0
            avg_price = cost / filled if filled > 0 else 0.0
            return filled, avg_price, "EXITO"
            
        return 0.0, 0.0, "FALLO"
    except asyncio.TimeoutError:
        print(f"⏰ TIMEOUT en {symbol}")
        return 0.0, 0.0, "TIMEOUT"
    except Exception as e:
        print(f"❌ Error: {e}")
        return 0.0, 0.0, "ERROR"

async def intentar_rescate(symbol_actual, cantidad_actual, moneda_actual):
    """
    🚑 PROTOCOLO DE EMERGENCIA (ROLLBACK)
    Intenta vender la moneda 'caliente' para volver a USDT.
    """
    print(f"\n🚨 EMERGENCIA: Iniciando Rescate de {cantidad_actual} {moneda_actual}...")
    
    # Buscamos par directo contra USDT (Ej: ETH -> ETH/USDT)
    par_rescate = f"{moneda_actual}/{MONEDA_BASE}"
    side = 'sell'
    
    # Caso especial: Si tenemos USDT, no hay nada que rescatar
    if moneda_actual == MONEDA_BASE:
        print("✅ Falsa alarma. Ya estamos en USDT.")
        return

    # Caso especial: Si la moneda es rara y el par es al revés (USDT/XXX), side=buy
    # (Poco probable en Binance con monedas principales, pero por seguridad)
    try:
        market = exchange.market(par_rescate)
    except:
        # Si no existe XXX/USDT, intentamos buscar ruta inversa o par BTC... 
        # Por simplicidad en v4, asumimos que todo tiene par USDT directo o BNB/BTC.
        print(f"💀 CRÍTICO: No encuentro par {par_rescate} para rescatar. Revisar manual.")
        return

    # Ejecutar venta de pánico
    print(f"🚑 VENDIENDO {par_rescate} a MERCADO...")
    filled, _, estado = await ejecutar_orden_mercado(par_rescate, side, cantidad_actual)
    
    if estado == "EXITO":
        print(f"✅ RESCATE EXITOSO. Capital recuperado en USDT.")
    else:
        print(f"💀 FALLÓ EL RESCATE. INTERVENCIÓN HUMANA REQUERIDA.")

async def procesar_arbitraje(payload):
    ruta = payload.get('ruta')
    print(f"\n🚀 EJECUTANDO RUTA: {ruta}")
    
    moneda_actual = MONEDA_BASE
    cantidad_actual = CAPITAL_INICIAL
    
    # State tracking para Rollback
    paso_actual = 0
    
    for i, symbol in enumerate(ruta):
        paso_actual = i + 1
        print(f"👉 Paso {paso_actual}: {symbol} (Tengo {cantidad_actual:.4f} {moneda_actual})")
        
        # 1. Análisis de Mercado
        try:
            market = exchange.market(symbol)
            base, quote = market['base'], market['quote']
        except:
            await exchange.load_markets()
            market = exchange.market(symbol)
            base, quote = market['base'], market['quote']

        # 2. Decisión de Side
        precio_ref = 0
        if moneda_actual == quote: # BUY
            side = 'buy'
            next_coin = base
            # Necesitamos precio para estimar cantidad base
            ticker = await exchange.fetch_ticker(symbol)
            precio_ref = ticker['last']
            qty_orden = cantidad_actual / precio_ref
        elif moneda_actual == base: # SELL
            side = 'sell'
            next_coin = quote
            qty_orden = cantidad_actual
        else:
            print("❌ Error de lógica de monedas.")
            return

        # Buffer de seguridad (Fees)
        qty_orden = qty_orden * 0.995

        # 3. EJECUCIÓN
        filled, precio_real, estado = await ejecutar_orden_mercado(symbol, side, qty_orden)
        
        if estado != "EXITO":
            print(f"🛑 FALLO EN PASO {paso_actual}. INICIANDO RESCATE.")
            if moneda_actual != MONEDA_BASE:
                await intentar_rescate(moneda_actual, cantidad_actual, moneda_actual)
            return

        # 4. Actualización de Saldos
        if side == 'buy': cantidad_actual = filled
        else: cantidad_actual = filled * precio_real
        moneda_actual = next_coin

    print(f"🏁 FIN. Saldo: {cantidad_actual:.4f} USDT | PnL: {cantidad_actual - CAPITAL_INICIAL:.4f}")

async def handle_client(reader, writer):
    """Server TCP Seguro"""
    try:
        while True:
            line = await reader.readline()
            if not line: break
            try:
                es_valido, payload = await validar_firma(json.loads(line.decode().strip()))
                if es_valido: await procesar_arbitraje(payload)
                else: print("⛔ Firma inválida")
            except: continue
    finally: writer.close()

async def main():
    print("🛡️ EXECUTOR v4.0 (Rollback Ready) Iniciando...")
    await exchange.load_markets()
    server = await asyncio.start_server(handle_client, HOST, PORT)
    print(f"👂 Escuchando en {HOST}:{PORT}")
    async with server: await server.serve_forever()

if __name__ == "__main__":
    try: asyncio.run(main())
    except: pass
    finally: asyncio.run(exchange.close())
