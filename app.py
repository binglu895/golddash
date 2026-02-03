import streamlit as st
import pandas as pd
import yfinance as yf
from fredapi import Fred
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import time
import os

# --- Page Configuration ---
st.set_page_config(
    page_title="Gold Market Research Dashboard",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Custom Styling ---
st.markdown("""
<style>
    .main {
        background-color: #0e1117;
    }
    .stMetric {
        background-color: #1e2130;
        padding: 15px;
        border-radius: 10px;
        border: 1px solid #3e4451;
    }
    [data-testid="stSidebar"] {
        background-color: #1e2130;
    }
    .stAlert {
        padding: 10px;
        border-radius: 5px;
    }
</style>
""", unsafe_allow_html=True)

# --- FRED API Key Configuration ---
# Securely fetch API key from st.secrets (Streamlit Cloud)
try:
    FRED_API_KEY = st.secrets["FRED_API_KEY"]
    os.environ["FRED_API_KEY"] = FRED_API_KEY
except KeyError:
    st.warning("⚠️ 未检测到 FRED_API_KEY。请在 Streamlit Secrets 中配置以确保数据抓取稳定。")
    # Fallback for local testing if needed: os.environ["FRED_API_KEY"] = "YOUR_KEY"

# --- Constants & Config ---
YF_TICKERS = {
    "Gold": "GC=F",
    "DXY": "DX-Y.NYB",
    "10Y_Nominal": "^TNX",
    "GLD": "GLD"
}

FRED_TICKERS = {
    "10Y_Real": "DFII10",
    "FedFunds": "FEDFUNDS",
    "SOFR": "SOFR"
}

# --- Data Fetching Logic ---
@st.cache_data(ttl=600)  # Cache for 10 minutes
def get_yfinance_data(tickers, period="1y"):
    series_list = []
    for name, ticker in tickers.items():
        try:
            df = yf.download(ticker, period=period, interval="1d", progress=False)
            if not df.empty:
                # Handle potential MultiIndex columns (yfinance sometimes returns them)
                if isinstance(df.columns, pd.MultiIndex):
                    # Usually the first level is 'Close' or similar, we want that
                    # But often it's multi-ticker multi-level. We just need the actual data column.
                    # Simplest way: just take the 'Close' column if it exists across levels
                    content = df['Close']
                    if isinstance(content, pd.DataFrame):
                        # If multiple tickers in one download (not our case but safer)
                        content = content.iloc[:, 0]
                else:
                    content = df['Close']
                
                content.name = name
                series_list.append(content)
        except Exception as e:
            st.error(f"Error fetching {name} ({ticker}): {e}")
    
    if not series_list:
        return pd.DataFrame()
        
    # Using pd.concat is much more robust than pd.DataFrame(dict)
    return pd.concat(series_list, axis=1)

@st.cache_data(ttl=3600)  # Cache for 1 hour
def get_fred_data(tickers, start_date):
    if not FRED_API_KEY or FRED_API_KEY == "YOUR_ACTUAL_FRED_API_KEY_HERE":
        st.error("FRED_API_KEY 未配置，请在 Streamlit Secrets 中设置。")
        return pd.DataFrame()
    
    try:
        fred = Fred(api_key=FRED_API_KEY)
        series_list = []
        # Increase lookback window slightly to ensure we get data
        buffer_start = start_date - timedelta(days=7)
        
        for name, ticker in tickers.items():
            try:
                series = fred.get_series(ticker, observation_start=buffer_start)
                if not series.empty:
                    series.name = name
                    series_list.append(series)
            except Exception as e:
                st.error(f"无法获取 {name} ({ticker}): {e}")
        
        if not series_list:
            return pd.DataFrame()
            
        df = pd.concat(series_list, axis=1)
        # Sort and ffill to handle different release schedules
        df = df.sort_index().ffill()
        return df[df.index >= pd.to_datetime(start_date)]
    except Exception as e:
        st.error(f"Error initializing FRED API: {e}")
        return pd.DataFrame()

# --- Main Application ---

st.title("💰 黄金市场投研 Dashboard")

# --- Sidebar ---
st.sidebar.header("控制面板")
time_range = st.sidebar.selectbox(
    "回溯时间范围",
    options=["1个月", "3个月", "1年", "2年"],
    index=2
)

# Map time range to yfinance period strings
period_map = {
    "1个月": "1mo",
    "3个月": "3mo",
    "1年": "1y",
    "2年": "2y"
}
y_period = period_map[time_range]

# Calculate start date for FRED
end_date = datetime.today()
if time_range == "1个月":
    start_date = end_date - timedelta(days=30)
elif time_range == "3个月":
    start_date = end_date - timedelta(days=90)
elif time_range == "1年":
    start_date = end_date - timedelta(days=365)
else:
    start_date = end_date - timedelta(days=730)

# --- Data Loading ---
with st.spinner("正在抓取实时数据..."):
    df_yf = get_yfinance_data(YF_TICKERS, period=y_period)
    df_fred = get_fred_data(FRED_TICKERS, start_date)

    # Note: df_yf and df_fred are already clean from the helper functions

# --- Core Logic & Calculations ---
# Merge all data
df_all = pd.concat([df_yf, df_fred], axis=1).ffill().dropna()

# Calculate Liquidity Spread: SOFR - FEDFUNDS
if "SOFR" in df_all.columns and "FedFunds" in df_all.columns:
    df_all["Liquidity_Spread"] = (df_all["SOFR"] - df_all["FedFunds"])
else:
    df_all["Liquidity_Spread"] = 0

# --- KPI Cards ---
col1, col2, col3, col4 = st.columns(4)

if not df_yf.empty:
    current_gold = df_yf["Gold"].iloc[-1]
    prev_gold = df_yf["Gold"].iloc[-2]
    gold_pct_change = ((current_gold - prev_gold) / prev_gold) * 100
    col1.metric("当前金价 (USD)", f"${current_gold:.2f}", f"{gold_pct_change:+.2f}%")

if not df_fred.empty:
    df_fred_clean = df_fred.dropna(subset=["10Y_Real", "FedFunds", "SOFR"], how='all').ffill()
    if not df_fred_clean.empty:
        real_rate = df_fred_clean["10Y_Real"].iloc[-1]
        ff = df_fred_clean["FedFunds"].iloc[-1]
        sofr = df_fred_clean["SOFR"].iloc[-1]
        
        # Check if we have both values for spread
        if not pd.isna(sofr) and not pd.isna(ff):
            current_spread = sofr - ff
            # Check threshold (0.1%)
            status_label = "正常" if abs(current_spread) < 0.1 else "偏离/流动性紧张"
            col3.metric("流动性利差 (SOFR-FF)", f"{current_spread:.3f}%", status_label, delta_color="inverse" if abs(current_spread) >= 0.1 else "normal")
        else:
            col3.metric("流动性利差 (SOFR-FF)", "数据不足", "获取中")
            current_spread = 0
    
        if not pd.isna(real_rate):
            col2.metric("10年期实际利率", f"{real_rate:.2f}%", delta=None)
        else:
            col2.metric("10年期实际利率", "数据不足", None)
    else:
        col2.metric("10年期实际利率", "数据不足", "无有效数据")

if "DXY" in df_yf.columns:
    current_dxy = df_yf["DXY"].iloc[-1]
    prev_dxy = df_yf["DXY"].iloc[-2]
    dxy_pct = ((current_dxy - prev_dxy) / prev_dxy) * 100
    col4.metric("美元指数 (DXY)", f"{current_dxy:.2f}", f"{dxy_pct:+.2f}%")

st.divider()

# --- Visualizations ---

# 图表1：黄金价格与 10 年期实际利率的叠加对比图（双坐标轴）
fig1 = make_subplots(specs=[[{"secondary_y": True}]])

fig1.add_trace(
    go.Scatter(x=df_all.index, y=df_all["Gold"], name="黄金价格 (GC=F)", line=dict(color="#FFD700", width=2)),
    secondary_y=False,
)

fig1.add_trace(
    go.Scatter(x=df_all.index, y=df_all["10Y_Real"], name="10Y 实际利率 (DFII10)", line=dict(color="#00CED1", width=2, dash='dot')),
    secondary_y=True,
)

fig1.update_layout(
    title_text="黄金价格 vs. 10年期实际利率 (负相关性分析)",
    template="plotly_dark",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
)

fig1.update_yaxes(title_text="黄金价格 (USD)", secondary_y=False)
fig1.update_yaxes(title_text="实际利率 (%)", secondary_y=True, autorange="reversed") # Real rates are often plotted reversed against gold

st.plotly_chart(fig1, use_container_width=True)

# 图表2：流动性利差图 (SOFR - FEDFUNDS)
fig2 = go.Figure()

fig2.add_trace(go.Scatter(
    x=df_all.index, y=df_all["Liquidity_Spread"],
    name="SOFR - FEDFUNDS",
    line=dict(color="#FF4B4B", width=2),
    fill='tozeroy'
))

# Add threshold lines
fig2.add_hline(y=0.1, line_dash="dash", line_color="orange", annotation_text="0.1% Alert")
fig2.add_hline(y=-0.1, line_dash="dash", line_color="orange")

fig2.update_layout(
    title_text="流动性利差 (SOFR - FEDFUNDS) 实时监控",
    xaxis_title="日期",
    yaxis_title="利差 (%)",
    template="plotly_dark"
)

st.plotly_chart(fig2, use_container_width=True)

# 图表3：美元指数近 30 日走势
df_dxy_30 = df_yf["DXY"].tail(30) if not df_yf.empty else pd.DataFrame()

if not df_dxy_30.empty:
    fig3 = go.Figure()
    fig3.add_trace(go.Scatter(
        x=df_dxy_30.index, y=df_dxy_30,
        mode='lines+markers',
        name='DXY',
        line=dict(color='#A9A9A9', width=3)
    ))
    
    fig3.update_layout(
        title_text="美元指数 (DXY) 近 30 日趋势",
        xaxis_title="日期",
        yaxis_title="指数点位",
        template="plotly_dark"
    )
    st.plotly_chart(fig3, use_container_width=True)

# --- Footer ---
st.caption("数据来源: Yahoo Finance (yfinance) & Federal Reserve Economic Data (FRED). 更新时间: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
