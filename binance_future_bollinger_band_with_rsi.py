import ccxt
import time
import datetime
import pandas as pd
import numpy as np
import math
import asyncio

binance_api = <BINANCE PUBLIC KEY>
binance_private = <BINANCE PRIVATE KEY>

binance_future = ccxt.binance(config={
    'apiKey':binance_api,
    'secret':binance_private,
    'enableRateLimit':True,
    'options':{
        'defaultType':'future'
    }})

#거래 심벌 세팅
btc_symbol = "BTC/BUSD"
eth_symbol = "ETH/BUSD"

#잔고 확인 및 잔고에 따른 각 코인별 거래액, 봉별 배율 세팅
free_balance = binance_future.fetch_balance(params={"type":"future"})
btc_balance = free_balance['BUSD']['free']/2
eth_balance = free_balance['BUSD']['free']/2
one_day_multiply = 3.75
four_hour_multiply = 3.75
one_hour_multiply = 1
fifteen_minute_multiply = 0.25

def get_ohlcv(symbol, timeframe):
    ohlcv = binance_future.fetch_ohlcv(
        symbol = symbol,
        timeframe = timeframe,
        since = None,
        limit = 25
    )

    df = pd.DataFrame(ohlcv, columns=['datetime', 'open', 'high', 'low', 'close', 'volume'])
    df['datetime'] = pd.to_datetime(df['datetime'], unit='ms')
    df.set_index('datetime', inplace=True)

    return df

def create_indicator(symbol, timeframe):
    raw_data = get_ohlcv(symbol, timeframe)
    raw_data['middle'] = raw_data['close'].rolling(window=20).mean()
    std = raw_data['close'].rolling(20).std(ddof=0)
    raw_data['upper'] = raw_data['middle'] + (2 * std)
    raw_data['lower'] = raw_data['middle'] - (2 * std)
    
    raw_data['change'] = raw_data['close'] - raw_data['close'].shift(1)
    raw_data['increase'] = np.where(raw_data['change'] >= 0, raw_data['change'], 0)
    raw_data['decrease'] = np.where(raw_data['change'] < 0, raw_data['change'].abs(), 0)

    #WMA : Wells Moving Average
    raw_data['AU'] = raw_data['increase'].ewm(alpha=1/14, min_periods=14).mean()
    raw_data['AD'] = raw_data['decrease'].ewm(alpha=1/14, min_periods=14).mean()
    raw_data['RSI'] = (raw_data['AU'] / (raw_data['AU'] + raw_data['AD'])) *100

    raw_data['bull'] = np.where(raw_data['high'] >= raw_data['upper'], True, False)
    raw_data['bear'] = np.where(raw_data['low'] <= raw_data['lower'], True, False)

    return raw_data

def cal_amount(balance, multiply, cur_price):
    trade_amount = balance * multiply
    amount = math.floor((trade_amount * 1000000)/cur_price) / 1000000

    return amount

def enter_position(symbol, cur_price, amount, position, long_target_price, short_target_price):
    position_info = {
        "type" : None,
        "amount" : 0
    }
    position_info['type'] = position
    position_info['amount'] = amount

    if position_info['type'] == 'long':
        target_price = long_target_price
        long_orders = [None] * 3
        long_orders[0] = binance_future.create_order(symbol=symbol, type="MARKET", side="buy", amount = amount)
        long_orders[1] = binance_future.create_order(symbol=symbol, type="TAKE_PROFIT_MARKET", side='sell', amount = amount, params={'stopPrice':target_price})
        long_orders[2] = binance_future.create_order(symbol=symbol, type="STOP_MARKET", side='sell', amount = amount, params={'stopPrice': cur_price * 0.97})

    elif position_info['type'] == 'short':
        target_price = short_target_price
        short_orders = [None] * 3
        short_orders[0] = binance_future.create_order(symbol=symbol, type="MARKET", side="sell", amount = amount)
        short_orders[1] = binance_future.create_order(symbol=symbol, type="TAKE_PROFIT_MARKET", side='buy', amount = amount, params={'stopPrice':target_price})
        short_orders[2] = binance_future.create_order(symbol=symbol, type="STOP_MARKET", side='buy', amount = amount, params={'stopPrice': cur_price * 1.03})

async def check_enter(symbol, timeframe, wait_time):
    indicator = create_indicator(symbol, timeframe)
    cur_price = float(binance_future.fetch_ticker(symbol)['info']['lastPrice'])
    symbol_balance = 0
    tf_multiply = 1

    if symbol == "BTC/BUSD":
        symbol_balance = btc_balance
    elif symbol == "ETH/BUSD":
        symbol_balance = eth_balance

    if timeframe == "1d":
        tf_multiply = one_day_multiply
    elif timeframe == "4h":
        tf_multiply = four_hour_multiply
    elif timeframe == "1h":
        tf_multiply = one_hour_multiply
    elif timeframe == "15m":
        tf_multiply = fifteen_minute_multiply
    
    if (cur_price > float(indicator['upper'][-1])) & (float(indicator['RSI'][-1]) >= 70):
        band = indicator.iloc[-4:-1]['high'].max() - indicator.iloc[-4:-1]['low'].min()
        buffer = indicator.iloc[-4:-1]['high'].max() - (band / 5)
        
        if cur_price <= buffer :
            if indicator['bull'][-2] == False | indicator['bull'][-3] == False | indicator['bull'][-4] == False :
                amount = cal_amount(symbol_balance, tf_multiply, cur_price)
                enter_position(symbol, cur_price, amount, 'short', 0, indicator['upper'][-1])
            else:
                pass
        else:
            pass
    
    elif (cur_price < float(indicator['lower'][-1])) & (float(indicator['RSI'][-1]) <=30):
        band = indicator.iloc[-4:-1]['high'].max() - indicator.iloc[-4:-1]['low'].min()
        buffer = indicator.iloc[-4:-1]['low'].min() + (band / 5)
        
        if cur_price >= buffer :
            if indicator['bear'][-2] == False | indicator['bear'][-3] == False | indicator['bear'][-4] == False :
                amount = cal_amount(symbol_balance, tf_multiply, cur_price)
                enter_position(symbol, cur_price, amount, 'long', indicator['lower'][-1], 0)
            else:
                pass
        else:
            pass

    await asyncio.sleep(wait_time)
                
async def main():
    btc_1_day = check_enter(btc_symbol, '1d', 86400)
    eth_1_day = check_enter(eth_symbol, '1d', 86400)
    btc_4_hour = check_enter(btc_symbol, '4h', 14400)
    eth_4_hour = check_enter(eth_symbol, '4h', 14400)
    btc_1_hour = check_enter(btc_symbol, '1h', 3600)
    eth_1_hour = check_enter(eth_symbol, '1h', 3600)
    btc_15_min = check_enter(btc_symbol, '15m', 3600)
    eth_15_min = check_enter(eth_symbol, '1h', 3600)

    await asyncio.gather(
        btc_1_day, btc_4_hour, btc_1_hour, btc_15_min,
        eth_1_day, eth_4_hour, eth_1_hour, eth_15_min
    )

while True:
    asyncio.run(main())
