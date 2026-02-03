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

st.markdown("""
<style>
    /* Minimalist Dark Theme */
    .main {
        background-color: #0b0e14;
        color: #e0e0e0;
    }
    
    /* KPI Cards - no borders, subtle shadows, clean font */
    [data-testid="stMetric"] {
        background-color: transparent !important;
        border: none !important;
        padding: 0px !important;
    }
    
    [data-testid="stMetricValue"] {
        font-size: 2.2rem !important;
        font-weight: 300 !important;
    }
    
    [data-testid="stMetricLabel"] {
        font-size: 0.9rem !important;
        font-weight: 400 !important;
        color: #888888;
        text-transform: uppercase;
        letter-spacing: 0.1em;
    }

    /* Interest Rate Group Highlight - Light Cards for Black Text */
    [data-testid="column"]:nth-of-type(2),
    [data-testid="column"]:nth-of-type(3),
    [data-testid="column"]:nth-of-type(4) {
        background-color: #ffffff !important;
        border-radius: 12px !important;
        padding: 20px !important;
        margin-top: 5px !important;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15) !important;
        border: 1px solid #e0e0e0 !important;
    }
    
    /* Target ALL children of metric value in these columns to be black */
    [data-testid="column"]:nth-of-type(2) [data-testid="stMetricValue"] div,
    [data-testid="column"]:nth-of-type(3) [data-testid="stMetricValue"] div,
    [data-testid="column"]:nth-of-type(4) [data-testid="stMetricValue"] div,
    [data-testid="column"]:nth-of-type(2) [data-testid="stMetricValue"] p,
    [data-testid="column"]:nth-of-type(3) [data-testid="stMetricValue"] p,
    [data-testid="column"]:nth-of-type(4) [data-testid="stMetricValue"] p {
        color: #000000 !important;
        -webkit-text-fill-color: #000000 !important;
    }

    [data-testid="column"]:nth-of-type(2) [data-testid="stMetricLabel"],
    [data-testid="column"]:nth-of-type(3) [data-testid="stMetricLabel"],
    [data-testid="column"]:nth-of-type(4) [data-testid="stMetricLabel"] {
        color: #333333 !important;
        font-weight: 500 !important;
    }

    /* Set other metrics back to white/light for the dark theme */
    [data-testid="column"]:nth-of-type(1) [data-testid="stMetricValue"] *,
    [data-testid="column"]:nth-of-type(5) [data-testid="stMetricValue"] *,
    [data-testid="column"]:nth-of-type(6) [data-testid="stMetricValue"] * {
        color: #ffffff !important;
    }

    /* Sidebar - dark and sleek with white text */
    [data-testid="stSidebar"] {
        background-color: #0E1117 !important;
        border-right: 1px solid #1c1f26;
    }

    [data-testid="stSidebar"] [data-testid="stHeading"] h2 {
        color: #FFD700 !important; /* 强制改为金色 */
        font-weight: 700 !important;
        letter-spacing: 1px;
        margin-bottom: -10px; /* 紧凑布局 */
    }

    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
    [data-testid="stSidebar"] .stMarkdown p {
        color: #FFFFFF !important; /* 确保普通段落文字为纯白 */
        opacity: 1 !important;
    }
    
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] [data-testid="stHeader"] {
        color: #ffffff !important;
    }
    
    /* Ensure all headers in sidebar are white */
    [data-testid="stSidebar"] h1, 
    [data-testid="stSidebar"] h2, 
    [data-testid="stSidebar"] h3 {
        color: #FFFFFF !important;
    }
    
    /* Divider - subtle line */
    hr {
        margin: 2em 0;
        border: 0;
        border-top: 1px solid #1c1f26;
    }

    /* Plotly charts backgrounds */
    .js-plotly-plot .plotly .main-svg {
        background: transparent !important;
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
    "10Y_Nominal_YF": "^TNX",  # Primary source for Nominal
    "GLD": "GLD",
    "FFF": "ZQ=F"               # 30-Day Fed Funds Futures
}

FRED_TICKERS = {
    "10Y_Breakeven_FRED": "T10YIE",  # Primary source for Breakeven
    "2Y_Nominal": "DGS2",
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
    df = pd.concat(series_list, axis=1)
    # Deduplicate index (keep last) to prevent reindexing errors
    return df.loc[~df.index.duplicated(keep='last')]

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
        # Deduplicate index (keep last)
        df = df.loc[~df.index.duplicated(keep='last')]
        # Sort and ffill to handle different release schedules
        df = df.sort_index().ffill()
        return df[df.index >= pd.to_datetime(start_date)]
    except Exception as e:
        st.error(f"Error initializing FRED API: {e}")
        return pd.DataFrame()

# --- Main Application ---

st.title("💰 黄金市场投研 Dashboard")

# --- Sidebar ---
st.sidebar.header("🕹️ 控制面板")
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
df_all = pd.concat([df_yf, df_fred], axis=1)

# Final deduplication
df_all = df_all.loc[~df_all.index.duplicated(keep='last')].ffill()

# Automated FedWatch Estimate (Prob No Change)
# Logic: If implied rate (100-Price) is near FedFunds, prob is high.
fedwatch_prob = 90 # Default fallback
if "FFF" in df_all.columns and "FedFunds" in df_all.columns:
    try:
        latest_fff = df_all["FFF"].dropna().iloc[-1]
        implied_rate = 100 - latest_fff
        current_ff = df_all["FedFunds"].dropna().iloc[-1]
        
        # Sensitivity: diff is how much market expects rate to drop
        diff = current_ff - implied_rate
        if diff <= 0:
            fedwatch_prob = 95
        elif diff >= 0.25:
            fedwatch_prob = 10
        else:
            # Linear interpolation between 95 and 10
            fedwatch_prob = int(95 - (diff / 0.25) * 85)
    except Exception:
        pass

# Drop rows where we don't have basic Price data
df_all = df_all.dropna(subset=["Gold"])

# Fisher Equation: Real Yield = Nominal (YF) - Breakeven (FRED)
if "10Y_Nominal_YF" in df_all.columns and "10Y_Breakeven_FRED" in df_all.columns:
    df_all["10Y_Real"] = df_all["10Y_Nominal_YF"] - df_all["10Y_Breakeven_FRED"]
else:
    df_all["10Y_Real"] = 0

# Calculate Fed Expectations (2Y - FedFunds)
if "2Y_Nominal" in df_all.columns and "FedFunds" in df_all.columns:
    df_all["Fed_Expectations"] = df_all["2Y_Nominal"] - df_all["FedFunds"]
else:
    df_all["Fed_Expectations"] = 0

# Calculate Liquidity Spread: SOFR - FEDFUNDS
if "SOFR" in df_all.columns and "FedFunds" in df_all.columns:
    df_all["Liquidity_Spread"] = (df_all["SOFR"] - df_all["FedFunds"])
else:
    df_all["Liquidity_Spread"] = 0

# --- KPI Cards ---
col1, col2, col3, col4, col5, col6 = st.columns(6)

if not df_yf.empty:
    current_gold = df_yf["Gold"].iloc[-1]
    prev_gold = df_yf["Gold"].iloc[-2]
    gold_pct_change = ((current_gold - prev_gold) / prev_gold) * 100
    col1.metric("金价 (USD)", f"${current_gold:.2f}", f"{gold_pct_change:+.2f}%")

if "10Y_Nominal_YF" in df_all.columns:
    col2.metric("10Y 名义利率(TNX)", f"{df_all['10Y_Nominal_YF'].iloc[-1]:.2f}%")

if "10Y_Breakeven_FRED" in df_all.columns:
    col3.metric("10Y 盈亏平衡(FRED)", f"{df_all['10Y_Breakeven_FRED'].iloc[-1]:.2f}%")

if "10Y_Real" in df_all.columns:
    real_rate = df_all["10Y_Real"].iloc[-1]
    col4.metric("10Y 实际利率", f"{real_rate:.2f}%")

if "Fed_Expectations" in df_all.columns:
    fed_exp = df_all["Fed_Expectations"].iloc[-1]
    exp_status = "降息预期强" if fed_exp < -0.2 else "中性"
    col5.metric("降息预期 (2Y-FF)", f"{fed_exp:.2f}%", exp_status)

if "DXY" in df_yf.columns:
    current_dxy = df_yf["DXY"].iloc[-1]
    prev_dxy = df_yf["DXY"].iloc[-2]
    dxy_pct = ((current_dxy - prev_dxy) / prev_dxy) * 100
    col6.metric("美元指数", f"{current_dxy:.2f}", f"{dxy_pct:+.2f}%")

st.divider()

# --- Macro Sentiment & Advice (SOP) ---
st.subheader("🔭 宏观情绪与交易建议")

# Calculate metrics for SOP
if "Fed_Expectations" in df_all.columns:
    current_spread = df_all["Fed_Expectations"].iloc[-1]
    
    # Logic Implementation
    # Scenario 1: Bearish
    if fedwatch_prob > 80 and current_spread > -0.15:
        box_bg = "rgba(255, 75, 75, 0.15)"
        box_border = "#FF4B4B"
        status_text = "🟥 宏观逆风 - 降息预期冰封"
        advice_text = "市场已接受高利率现实，黄金缺乏向上动能。建议逢高减仓，等待 10Y 实际利率回落。"
    # Scenario 2: Divergence
    elif fedwatch_prob > 80 and current_spread < -0.30:
        box_bg = "rgba(255, 165, 0, 0.15)"
        box_border = "#FFA500"
        status_text = "🟨 背离警报 - 资金抢跑降息"
        advice_text = "尽管美联储嘴硬，但债券市场在强行定价未来降息。黄金可能出现“利空出尽”的暴力反弹。建议：左侧分批埋伏多单。"
    # Scenario 3: Bullish
    elif fedwatch_prob < 50 and current_spread < -0.40:
        box_bg = "rgba(0, 204, 102, 0.15)"
        box_border = "#00CC66"
        status_text = "🟩 极度利多 - 降息周期开启"
        advice_text = "市场达成降息共识。建议：顺势做多，直到实际利率跌破 1.5%。"
    else:
        box_bg = "rgba(128, 128, 128, 0.1)"
        box_border = "#BBBBBB"
        status_text = "⬜ 市场中性 - 震荡整理"
        advice_text = "宏观信号暂不明确，建议观望或进行区间波段操作。"

    st.markdown(f"""
    <div style="background-color: {box_bg}; border-left: 5px solid {box_border}; padding: 20px; border-radius: 10px; border: 1px solid {box_bg.replace('0.15', '0.3')}; margin-bottom: 25px;">
        <h3 style="margin-top: 0px; color: {box_border}; font-size: 1.3rem;">{status_text}</h3>
        <p style="margin-bottom: 10px; font-size: 1.1rem; color: #FFFFFF; line-height: 1.6; font-weight: 500;">
            <b>交易建议：</b>{advice_text}
        </p>
        <a href="https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html" style="color: #BBBBBB; font-size: 0.8rem; text-decoration: none;">🔗 数据来源：CME FedWatch Tool (基于 ZQ=F 期货自动估算: {fedwatch_prob}%)</a>
    </div>
    """, unsafe_allow_html=True)
else:
    st.info("数据加载中，暂无法生成宏观分析...")

# --- Visualizations ---

# 图表1：黄金价格与 10 年期实际利率的叠加对比图（双坐标轴）
fig1 = make_subplots(specs=[[{"secondary_y": True}]])

fig1.add_trace(
    go.Scatter(x=df_all.index, y=df_all["Gold"], name="黄金价格 (GC=F)", line=dict(color="#FFD700", width=2)),
    secondary_y=False,
)

fig1.add_trace(
    go.Scatter(x=df_all.index, y=df_all["10Y_Real"], name="10Y 实际利率 (Calculated)", line=dict(color="#00CED1", width=2, dash='dot')),
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

# 图表3：宏观情绪对比图 (不降息概率 vs. 利差)
fig_macro = make_subplots(specs=[[{"secondary_y": True}]])

# We use current user input for probability representation (historically flat for context if no history)
# Note: For better visualization, we show the 2Y-FF spread trend and indicate the probability level
fig_macro.add_trace(
    go.Scatter(x=df_all.index, y=df_all["Fed_Expectations"], name="2Y-FF 利差 (Spread)", line=dict(color="#00FFAA", width=2)),
    secondary_y=False,
)

# Dummy series for Probability to create secondary axis scale
fig_macro.add_trace(
    go.Bar(x=[df_all.index[-1]], y=[fedwatch_prob], name="3月不降息概率 (Spot)", marker_color="rgba(255, 75, 75, 0.4)", width=1000000000), 
    secondary_y=True,
)

fig_macro.update_layout(
    title_text="宏观预期共振分析 (Spread vs. FedWatch Prob)",
    template="plotly_dark",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
)

fig_macro.update_yaxes(title_text="2Y-FFSpread (%)", secondary_y=False)
fig_macro.update_yaxes(title_text="不降息概率 (%)", secondary_y=True, range=[0, 100])

st.plotly_chart(fig_macro, use_container_width=True)

# 图表4：美元指数近 30 日走势
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
