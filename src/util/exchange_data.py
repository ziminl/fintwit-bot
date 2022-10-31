import ccxt.async_support as ccxt
import pandas as pd
from util.vars import stables

async def get_data(row) -> pd.DataFrame:
    
    exchange_info = {'apiKey': row["key"], 'secret': row["secret"]}
    
    if row['exchange'] == 'binance':
        exchange = ccxt.binance(exchange_info)
    elif row['exchange'] == 'kucoin':
        exchange_info['password'] = row['passphrase']
        exchange = ccxt.kucoin(exchange_info)
        
    balances = await get_balance(exchange)
    
    # Create a list of dictionaries
    owned = []

    for symbol, amount in balances.items():
        usd_val = await get_usd_price(exchange, symbol)
        worth = amount * usd_val
    
        if worth < 5:
            continue
        
        buying_price = await get_buying_price(exchange, symbol)
        
        if buying_price != 0:
            owned.append({
                "asset": symbol,
                "buying_price" : buying_price,
                "owned": amount,
                "exchange": exchange.id,
            })

    df = pd.DataFrame(owned)
    
    if not df.empty:
        df = df.astype({"asset": str, "buying_price": float, "owned": float, "exchange": str})
        
    await exchange.close()
    return df

async def get_balance(exchange) -> dict:
    balances = await exchange.fetchBalance()
    return {k: v for k, v in balances['total'].items() if v > 0}

async def get_usd_price(exchange, symbol) -> float:
    """
    Returns the price of the symbol in USD
    Symbol must be in the format 'BTC/USDT'
    """
    if symbol not in stables:
        for usd in stables:
            try:
                price = await exchange.fetchTicker(f"{symbol}/{usd}")
                if price != 0:
                    return price['last']
            except ccxt.BadSymbol:
                continue
    else:
        try:
            price = await exchange.fetchTicker(symbol + '/DAI')
            return price['last']
        except ccxt.BadSymbol:
            return 1
    
    return 0

async def get_buying_price(exchange, symbol) -> float:
    # Maybe try different quote currencies when returned list is empty
    if symbol in stables:
        return 1
    
    params = {}
    if exchange.id == 'kucoin':
        params = {"side" : 'buy'}
    
    try:
        trades = await exchange.fetchClosedOrders(f"{symbol}/USDT", params = params)
    except ccxt.BadSymbol:
        return 0
    if type(trades) == list:
        if len(trades) > 1:
            if exchange.id == 'binance':
                # Filter list for side:buy
                trades = [trade for trade in trades if trade['info']['side'] == 'BUY']
                if len(trades) == 0:
                    return 0
                
            return float(trades[-1]['price'])
        
    return 0