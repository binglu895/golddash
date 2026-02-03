import yfinance as yf
import pandas as pd
import pandas_datareader.data as web
from datetime import datetime, timedelta

def verify_data():
    print("--- Verification Report ---")
    
    # yfinance
    tickers = {"Gold": "GC=F", "DXY": "DX-Y.NYB"}
    print(f"Fetching yfinance data for: {list(tickers.keys())}...")
    df_yf = yf.download(list(tickers.values()), period="1mo", interval="1d", progress=False)['Close']
    
    if not df_yf.empty:
        gold_latest = df_yf["GC=F"].iloc[-1]
        dxy_latest = df_yf["DX-Y.NYB"].iloc[-1]
        print(f"Latest Gold Price: ${gold_latest:.2f}")
        print(f"Latest DXY Index: {dxy_latest:.2f}")

    # FRED
    fred_tickers = {"10Y_Real": "DFII10", "FedFunds": "FEDFUNDS", "SOFR": "SOFR"}
    start_date = datetime.today() - timedelta(days=30)
    buffer_start = start_date - timedelta(days=7)
    print(f"Fetching FRED data...")
    try:
        df_fred = web.DataReader(list(fred_tickers.values()), "fred", buffer_start)
        df_fred = df_fred.ffill()
        if not df_fred.empty:
            real_rate = df_fred["DFII10"].iloc[-1]
            ff = df_fred["FEDFUNDS"].iloc[-1]
            sofr = df_fred["SOFR"].iloc[-1]
            print(f"Latest Real Rate: {real_rate:.2f}%")
            print(f"Latest SOFR: {sofr:.3f}%")
            print(f"Latest Fed Funds: {ff:.3f}%")
            print(f"Current Spread: {sofr - ff:.3f}%")
        else:
            print("Error: FRED data is empty.")
    except Exception as e:
        print(f"Error fetching FRED: {e}")

if __name__ == "__main__":
    verify_data()
