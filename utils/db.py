import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
# import supabase # User needs to install supabase-py: pip install supabase

# Mock Supabase client if library not installed or secrets missing
try:
    from supabase import create_client, Client
except ImportError:
    create_client = None
    Client = None

class SupabaseHandler:
    def __init__(self):
        self.client = None
        self.enabled = False
        
        try:
            url = st.secrets["SUPABASE_URL"]
            key = st.secrets["SUPABASE_KEY"]
            if create_client and url and key:
                self.client = create_client(url, key)
                self.enabled = True
            else:
                print("Supabase client not initialized: Missing library or secrets.")
        except Exception as e:
            print(f"Supabase init error: {e}")

    def fetch_data(self, ticker: str, start_date: datetime) -> pd.DataFrame:
        """
        Fetch data from Supabase 'market_data' table.
        Schema: id, date, ticker, value, source, created_at
        """
        if not self.enabled:
            return pd.DataFrame()
            
        try:
            # Fetch data for the specific ticker after start_date
            response = self.client.table("market_data") \
                .select("date, value") \
                .eq("ticker", ticker) \
                .gte("date", start_date.strftime("%Y-%m-%d")) \
                .order("date", desc=False) \
                .execute()
                
            data = response.data
            if data:
                df = pd.DataFrame(data)
                df['date'] = pd.to_datetime(df['date'])
                df.set_index('date', inplace=True)
                df.rename(columns={'value': ticker}, inplace=True)
                return df
        except Exception as e:
            print(f"Error fetching from Supabase for {ticker}: {e}")
            
        return pd.DataFrame()

    def save_data(self, df: pd.DataFrame, ticker: str, source: str = "yahoo"):
        """
        Save/Upsert data to Supabase.
        Expects df with DateTime index and a column named or mapped to value.
        """
        if not self.enabled or df.empty:
            return

        try:
            # Prepare records
            records = []
            for date, row in df.iterrows():
                val = row.iloc[0] # Assuming single column series or first column
                if pd.isna(val): continue
                
                records.append({
                    "date": date.strftime("%Y-%m-%d"),
                    "ticker": ticker,
                    "value": float(val),
                    "source": source,
                    "updated_at": datetime.now().isoformat()
                })
            
            # Upsert (requires unique constraint on ticker + date in DB)
            if records:
                self.client.table("market_data").upsert(records, on_conflict="ticker, date").execute()
                print(f"Saved {len(records)} records for {ticker}")
                
        except Exception as e:
            print(f"Error saving to Supabase for {ticker}: {e}")
