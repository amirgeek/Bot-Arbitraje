kkimport asyncio
import json
import socket
import ccxt.async_support as ccxt
from config import API_KEY, SECRET_KEY, CAPITAL_INICIAL, HOST, PORT

# --- SETTINGS ---
TIMEOUT_ORDEN = 5      # Max wait seconds
MONEDA_BASE = 'USDT'   # Base asset

# Setup Exchange (Optimized headers)
exchange = ccxt.binance({
    'apiKey': API_KEY,
    'secret': SECRET_KEY,
    'options': {
        'defaultType': 'spot',
        'adjustForTimeDifference': True,
        'recvWindow': 10000 
    }
})

async def obtener_ticker_rapido(symbol):
    """Helper para obtener last price rapido"""
    try:
        ticker = await exchange.fetch_ticker(symbol)
        return ticker['last']
    except:
        return None

async def ejecutar_orden_mercado(symbol, side, cantidad):
    """
    Ejecucion Market Order.
    Returns: (filled, avg_price, status)
    """
    try:
        print(f"Executing {side.upper()} {symbol} Qty: {cantidad} (MARKET)...")
        
        # Normalizacion de precision para evitar errores de Binance
        qty_precisa = exchange.amount_to_precision(symbol, cantidad)
        
        # Fire order
        orden = await exchange.create_order(symbol, 'market', side, qty_precisa)
        
        # Check status inmediato
        if orden['status'] == 'closed' or orden['filled'] > 0:
            filled = float(orden['filled'])
            cost = float(orden['cost']) 
            avg_price = cost / filled if filled > 0 else 0
            print(f"   >> FILL: {filled} @ {avg_price:.4f}")
            return filled, avg_price, "EXITO"
        else:
            print("   >> Warning: Orden enviada pero sin fill.")
            return 0.0, 0.0, "FALLO"

    except Exception as e:
        print(f"   >> Exception Critical: {e}")
        return 0.0, 0.0, "ERROR"

async def procesar_arbitraje(ruta):
    """
    Main Loop Triangular: USDT -> A -> B -> USDT
    """
    print(f"\nTrigger: {ruta}")
    
    # State tracking
    moneda_actual = MONEDA_BASE
    cantidad_actual = CAPITAL_INICIAL
    
    # Loop de 3 steps
    for i, symbol in enumerate(ruta):
        print(f"Step {i+1}: {symbol} (Hold: {cantidad_actual:.4f} {moneda_actual})")
        
        # 1. Determinar base/quote para saber side
        try:
            market = exchange.market(symbol)
            base = market['base']
            quote = market['quote']
        except:
            await exchange.load_markets()
            market = exchange.market(symbol)
            base = market['base']
            quote = market['quote']

        # 2. Logica dinamica de Side
        if moneda_actual == quote:
            side = 'buy'
            next_coin = base
            # Calculo estimado de amount en base currency
            precio_ref = await obtener_ticker_rapido(symbol)
            qty_orden = cantidad_actual / precio_ref
        
        elif moneda_actual == base:
            side = 'sell'
            next_coin = quote
            qty_orden = cantidad_actual
            
        else:
            print(f"Error Mapping: Tengo {moneda_actual} pero par es {base}/{quote}.")
            return # Abort

        # Safety buffer de fees (0.5%)
        qty_orden = qty_orden * 0.995

        # 3. Exec
        filled, precio_real, estado = await ejecutar_orden_mercado(symbol, side, qty_orden)
        
        if estado != "EXITO":
            print(f"FAIL en Step {i+1}. Abortando ciclo.")
            # TODO: Implementar logica de Rollback/Rescue si falla step 2 o 3
            return

        # 4. Update balances virtuales
        if side == 'buy':
            cantidad_actual = filled
        else:
            cantidad_actual = filled * precio_real

        moneda_actual = next_coin 

    # --- Summary ---
    print(f"Cycle End. Final Balance: {cantidad_actual:.4f} {moneda_actual}")
    pnl = cantidad_actual - CAPITAL_INICIAL
    if pnl > 0:
        print(f"PROFIT: {pnl:.4f} USDT")
    else:
        print(f"LOSS (Fees/Slip): {pnl:.4f} USDT")


async def main():
    await exchange.load_markets() # Preload markets
    print("Markets loaded.")
    
    # Socket setup (Non-blocking)
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(1)
    server.setblocking(False)
    
    print(f"Executor Listening on {HOST}:{PORT}")
    print(f"Mode: MARKET ORDERS (Fast)")
    
    loop = asyncio.get_event_loop()
    
    while True:
        try:
            client, _ = await loop.sock_accept(server)
            data_raw = await loop.sock_recv(client, 4096)
            if data_raw:
                mensaje = json.loads(data_raw.decode())
                if 'ruta' in mensaje:
                    await procesar_arbitraje(mensaje['ruta'])
            client.close()
        except KeyboardInterrupt:
            break
        except Exception as e:
            await asyncio.sleep(0.01)

    await exchange.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutdown...")
