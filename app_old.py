import streamlit as st
import pandas as pd
import yfinance as yf
from fredapi import Fred
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import os
import sys

# Ensure utils can be imported
sys.path.append(os.getcwd())
# from utils.db import SupabaseHandler # Dynamic import later to handle missing deps

# --- Configuration ---
st.set_page_config(layout="wide", page_title="Gold Professional Dashboard", page_icon="🏦")

# Minimalist Style Injection
st.markdown("""
<style>
    .reportview-container {
        background: #0e1117;
    }
    .main .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }
    h1, h2, h3 {
        font-family: 'Helvetica Neue', sans-serif;
        font-weight: 300;
        letter-spacing: -0.5px;
    }
    .metric-card {
        background-color: #1c1f26;
        border: 1px solid #2d3139;
        padding: 15px;
        border-radius: 8px;
        text-align: center;
    }
    .stAlert {
        padding: 0.5rem;
        margin-bottom: 0.5rem;
    }
    div[data-testid="stMetricValue"] {
        font-size: 1.8rem;
    }
</style>
""", unsafe_allow_html=True)

# --- Secrets & Setup ---
try:
    FRED_API_KEY = st.secrets["FRED_API_KEY"]
except:
    st.error("Missing FRED_API_KEY")
    st.stop()

# --- Data Constants ---
YF_TICKERS = {
    "Gold": "GC=F",
    "DXY": "DX-Y.NYB",
    "VIX": "^VIX",
    "GVZ": "^GVZ",
    "USDCNY": "USDCNY=X",
    "GLD": "GLD",
    "10Y_Nominal": "^TNX"
}

FRED_TICKERS = {
    "10Y_TIPS": "DFII10", # Real Yield
    "10Y_Breakeven": "T10YIE",
    "Debt_to_GDP": "GFDEGDQ188S",
    "FedFunds": "FEDFUNDS", 
    "Interest_Expense": "A091RC1Q027SBEA" # Interest payments
}

# --- Supabase Setup ---
# Initialize Supabase
# db = SupabaseHandler() # We'll just define a dummy for now if import fails
class DummyDB:
    def fetch_data(self, t, s): return pd.DataFrame()
    def save_data(self, d, t, s): pass

try:
    from utils.db import SupabaseHandler
    db = SupabaseHandler()
except:
    db = DummyDB()

# --- Helper Functions ---
@st.cache_data(ttl=3600)
def get_combined_data(days=730):
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    # 1. Fetch YFinance
    yf_data = {}
    for name, ticker in YF_TICKERS.items():
        # Try DB first (Not implemented fully for YF as getting bulk is easier via API for now, 
        # but for production we'd fetch DB then API for missing)
        # For simplicity in this refactor, we fetch API then save to DB
        try:
            df = yf.download(ticker, start=start_date, progress=False)
            if not df.empty:
                # Handle MultiIndex if present
                if isinstance(df.columns, pd.MultiIndex):
                    df = df['Close']
                elif 'Close' in df.columns:
                    df = df[['Close']]
                else:
                    df = df.iloc[:, 0].to_frame()
                
                df.columns = ['Close']
                yf_data[name] = df['Close']
                
                # Async save or just save (might slow down first run)
                # db.save_data(df, name, "yahoo") 
        except Exception as e:
            st.warning(f"Failed {name}: {e}")

    # 2. Fetch FRED
    fred = Fred(api_key=FRED_API_KEY)
    fred_data = {}
    for name, ticker in FRED_TICKERS.items():
        try:
            # Check DB
            # db_df = db.fetch_data(name, start_date)
            # if not db_df.empty:
            #    fred_data[name] = db_df[name]
            # else:
            s = fred.get_series(ticker, observation_start=start_date)
            fred_data[name] = s
            # db.save_data(s.to_frame(name), name, "fred")
        except:
            pass
            
    # Combine
    df_all = pd.DataFrame(yf_data).join(pd.DataFrame(fred_data), how='outer')
    return df_all.ffill()

# --- Main App ---
st.title("🏛️ Institutional Gold Trader Dashboard")
st.caption("Macro Drive · Funds Flow · Technical Execution")

with st.spinner("Aggregating Multi-Source Data..."):
    df = get_combined_data()

if df.empty:
    st.error("No data available.")
    st.stop()

# Get latest valid data
latest = df.iloc[-1]
prev = df.iloc[-2]

# --- Layer 1: Macro Drive (The "Why") ---
st.markdown("### 1. Macro Drive (Direction)")
st.caption("Is Gold Mispriced relative to Real Rates & Dollar Credit?")

col1, col2, col3 = st.columns(3)

# 1.1 Real Rates Logic
real_rate = latest.get("10Y_TIPS", 0)
gold_price = latest.get("Gold", 0)
fair_value_model = 3000 - (real_rate * 200) # Dummy model: Rate up 1% -> Gold down 200
mispricing = gold_price - fair_value_model

with col1:
    st.metric("10Y Real Rate (TIPS)", f"{real_rate:.2f}%", f"{real_rate - prev.get('10Y_TIPS', 0):.2f}%", delta_color="inverse")
    if real_rate > 2.0:
        st.error("🛑 Bearish: Rates Restrictive")
    elif real_rate < 1.0:
        st.success("🟢 Bullish: Rates Accommodative")
    else:
        st.warning("⚪ Neutral")

# 1.2 Chart: Gold vs Real Rates (Inverted)
fig_macro = make_subplots(specs=[[{"secondary_y": True}]])
fig_macro.add_trace(go.Scatter(x=df.index, y=df["Gold"], name="Gold", line=dict(color="#FFD700")), secondary_y=False)
fig_macro.add_trace(go.Scatter(x=df.index, y=df["10Y_TIPS"], name="Real Yield (Inv)", line=dict(color="#00FFFF")), secondary_y=True)
fig_macro.update_yaxes(title_text="Gold", secondary_y=False)
fig_macro.update_yaxes(title_text="Real Yield (%)", reversed=True, secondary_y=True)
fig_macro.update_layout(title="Gold vs Real Rates (Correlation Check)", height=350, margin=dict(l=0,r=0,t=30,b=0))
st.plotly_chart(fig_macro, use_container_width=True)

# --- Layer 2: Funds Flow (The "Who") ---
st.markdown("---")
st.markdown("### 2. Funds Flow (Counterparty)")
st.caption("Are we following the Smart Money or getting Trapped?")

col_f1, col_f2 = st.columns(2)

# Placeholder logic for CFTC (Assuming simulated if missing)
cftc_net = 250000 # Mock high value
cftc_percentile = 95 

with col_f1:
    st.metric("CFTC Net Longs (Simulated)", f"{cftc_net:,.0f}", "Extreme High")
    if cftc_percentile > 90:
        st.error(f"⚠️ Crowded Trade: {cftc_percentile}th Percentile. Risk of Liquidation.")
    else:
        st.info("Funds Positioning Normal")

# GLD Divergence Logic
gld_holdings = latest.get("GLD", 0) # This is Price, implies holdings roughly (correlation). Real holdings need specific ticker.
# Converting GLD price to rough tonnage or just using price trend divergence

# --- Layer 3: Technical Execution (The "Where") ---
st.markdown("---")
st.markdown("### 3. Execution (Key Levels)")
st.caption("Liquidity Zones & Pivot Points")

# Calculate Pivots
high = df["Gold"].rolling(5).max().iloc[-1]
low = df["Gold"].rolling(5).min().iloc[-1]
close = latest["Gold"]
pp = (high + low + close) / 3
s1 = 2 * pp - high
r1 = 2 * pp - low

t_col1, t_col2, t_col3 = st.columns(3)
t_col1.metric("Pivot Point", f"${pp:.1f}")
t_col2.metric("Support 1 (Buy Zone)", f"${s1:.1f}")
t_col3.metric("Resistance 1 (Sell Zone)", f"${r1:.1f}")

# Cross-Border Arb
usdcny = latest.get("USDCNY", 7.2)
au_td_price = gold_price / 31.1035 * usdcny + 10 # Mock premium
premium = au_td_price - (gold_price / 31.1035 * usdcny)

if premium > 15:
    st.warning(f"🇨🇳 Domestic Premium High (+{premium:.1f}). Arb Window Open.")
else:
    st.info(f"Domestic Premium Normal (+{premium:.1f})")

# --- Layer 4: Reference ---
with st.expander("📚 Reference: Central Bank & Forecasts", expanded=False):
    st.write("Central Bank Holdings data would go here...")
    st.write("Forecast table would go here...")

