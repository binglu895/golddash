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
    "FFF": "ZQ=F",              # 30-Day Fed Funds Futures
    "VIX": "^VIX",              # Equity Volatility
    "GVZ": "^GVZ",              # Gold Volatility
    "USDCNY": "USDCNY=X",       # FX Rate
    "DomGold": "600489.SS"      # Domestic Gold Proxy (Shandong Gold)
}

FRED_TICKERS = {
    "10Y_Breakeven_FRED": "T10YIE",  # Primary source for Breakeven
    "2Y_Nominal": "DGS2",
    "FedFunds": "FEDFUNDS",
    "SOFR": "SOFR",
    "Interest_to_GDP": "A091RC1Q027SBEA", # Interest payments on federal debt
    "Federal_Debt_GDP": "GFDEGDQ188S",     # Federal Debt as % of GDP
    "CFTC_Net": "COMGOLDNET"               # CFTC Gold Non-Commercial Net Positions
}

# --- Data Fetching Logic ---
@st.cache_data(ttl=600)  # Cache for 10 minutes
def get_yfinance_data(tickers, period="2y"):
    series_list = []
    for name, ticker in tickers.items():
        try:
            # We always fetch a larger period ("2y") to ensure availability 
            # for 1mo/3mo slices which are prone to empty returns in some APIs
            df = yf.download(ticker, period="2y", interval="1d", progress=False)
            if not df.empty:
                # Robust extraction for newer yfinance MultiIndex
                if isinstance(df.columns, pd.MultiIndex):
                    if 'Close' in df.columns.get_level_values(0):
                        content = df['Close']
                    else:
                        content = df.iloc[:, 0] # Fallback to first column
                else:
                    if 'Close' in df.columns:
                        content = df['Close']
                    else:
                        content = df.iloc[:, 0]
                
                # If still a DataFrame (multiple columns under 'Close'), take the first
                if isinstance(content, pd.DataFrame):
                    content = content.iloc[:, 0]
                
                content.name = name
                series_list.append(content)
            else:
                st.warning(f"⚠️ {name} ({ticker}) 返回数据为空。")
        except Exception as e:
            st.error(f"Error fetching {name} ({ticker}): {e}")
    
    if not series_list:
        return pd.DataFrame()
        
    df = pd.concat(series_list, axis=1)
    return df.loc[~df.index.duplicated(keep='last')]

@st.cache_data(ttl=3600)  # Cache for 1 hour
def get_fred_data(tickers, start_date):
    if not FRED_API_KEY or FRED_API_KEY == "YOUR_ACTUAL_FRED_API_KEY_HERE":
        st.error("FRED_API_KEY 未配置，请在 Streamlit Secrets 中设置。")
        return pd.DataFrame()
    
    try:
        fred = Fred(api_key=FRED_API_KEY)
        series_list = []
        # Increase lookback window significantly for quarterly data (Interest to GDP etc.)
        buffer_start = start_date - timedelta(days=150) 
        
        for name, ticker in tickers.items():
            try:
                series = fred.get_series(ticker, observation_start=buffer_start)
                if not series.empty:
                    series.name = name
                    series_list.append(series)
                else:
                    st.warning(f"⚠️ FRED 指标 {name} ({ticker}) 无有效数据。")
            except Exception as e:
                st.error(f"无法获取 {name} ({ticker}): {e}")
        
        if not series_list:
            return pd.DataFrame()
            
        df = pd.concat(series_list, axis=1)
        df = df.loc[~df.index.duplicated(keep='last')]
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
    # Always fetch 2y baseline, slicing will happen later
    df_yf = get_yfinance_data(YF_TICKERS, period="2y")
    df_fred = get_fred_data(FRED_TICKERS, start_date)

    # Note: df_yf and df_fred are already clean from the helper functions

# Merge all data
df_all = pd.concat([df_yf, df_fred], axis=1)

# Final deduplication
df_all = df_all.loc[~df_all.index.duplicated(keep='last')].ffill()

# --- Slicing Logic ---
# Crop the data to the user's selected start_date after the ffill
# This ensures we have the latest data even if today's quote is late
df_all = df_all[df_all.index >= pd.to_datetime(start_date)]

# --- Technical & Execution Logic ---
# 1. 200-day Moving Average (using baseline df_yf before slice for accuracy)
if "Gold" in df_yf.columns:
    df_all["200MA"] = df_yf["Gold"].rolling(window=200).mean().reindex(df_all.index)

# 2. Pivot Points (based on yesterday's full data from yfinance)
pivot_p, pivot_r1, pivot_r2, pivot_s1, pivot_s2 = 0, 0, 0, 0, 0
if len(df_yf) > 2:
    try:
        y_high = df_yf["Gold"].shift(1).iloc[-1]
        y_low = df_yf["Gold"].shift(1).iloc[-1] # Simplification if H/L not separate in Close-only fetch
        # Re-fetch for H/L if possible, but for demo we use yesterday's close context
        y_close = df_yf["Gold"].shift(1).iloc[-1]
        
        # Real H/L if available
        pivot_p = (y_high + y_low + y_close) / 3
        pivot_r1 = 2 * pivot_p - y_low
        pivot_s1 = 2 * pivot_p - y_high
        pivot_r2 = pivot_p + (y_high - y_low)
        pivot_s2 = pivot_p - (y_high - y_low)
    except: pass

# 3. Domestic Premium Calculation
if "Gold" in df_all.columns and "USDCNY" in df_all.columns:
    df_all["Fair_CNY"] = (df_all["Gold"] / 31.1035) * df_all["USDCNY"]
    df_all["Dom_Spot"] = df_all["Fair_CNY"] + 8.5 # Simulated premium
    df_all["Premium"] = df_all["Dom_Spot"] - df_all["Fair_CNY"]
else:
    df_all["Premium"] = 0

# 4. Automated FedWatch Estimate (Prob No Change)
fedwatch_prob = 90
if "FFF" in df_all.columns and "FedFunds" in df_all.columns:
    try:
        latest_fff = df_all["FFF"].dropna().iloc[-1]
        implied_rate = 100 - latest_fff
        current_ff = df_all["FedFunds"].dropna().iloc[-1]
        diff = current_ff - implied_rate
        if diff <= 0: fedwatch_prob = 95
        elif diff >= 0.25: fedwatch_prob = 10
        else: fedwatch_prob = int(95 - (diff / 0.25) * 85)
    except: pass

# Drop rows where we don't have basic Price data
if "Gold" in df_all.columns:
    df_all = df_all.dropna(subset=["Gold"])
else:
    st.error("❌ 基础金价数据 (Gold) 抓取失败。这可能是由于网络问题或数据源暂时不可用。")
    st.info("尝试检查你的网络连接或稍后刷新页面。")
    st.stop()

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
col1, col2, col3, col4, col5, col6, col7 = st.columns(7)

if not df_yf.empty:
    current_gold = df_yf["Gold"].iloc[-1]
    prev_gold = df_yf["Gold"].iloc[-2]
    gold_pct_change = ((current_gold - prev_gold) / prev_gold) * 100
    col1.metric("金价 (USD)", f"${current_gold:.2f}", f"{gold_pct_change:+.2f}%")

current_premium = df_all["Premium"].iloc[-1] if "Premium" in df_all.columns else 0
prem_color = "normal" if current_premium < 15 else "inverse"
col7.metric("内外溢价 (CNY/g)", f"{current_premium:.2f}", delta=None, delta_color=prem_color)
if current_premium > 15:
    st.sidebar.warning(f"⚠️ 国内买盘过热 (溢价: {current_premium:.2f})")

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
    # Logic Implementation
    # Sentiment Weighting
    vix_val = df_all["VIX"].iloc[-1] if "VIX" in df_all.columns else 0
    gvz_val = df_all["GVZ"].iloc[-1] if "GVZ" in df_all.columns else 0
    gold_is_up = gold_pct_change > 0 if 'gold_pct_change' in locals() else False
    gold_is_high = df_all["Gold"].iloc[-1] > df_all["Gold"].rolling(20).mean().iloc[-1] if len(df_all) > 20 else False
    
    # Capital Flow Weighting
    cftc_val = df_all["CFTC_Net"].iloc[-1] if "CFTC_Net" in df_all.columns else 0
    gld_flow_neg = False
    if "Gold" in df_all.columns and "GLD" in df_all.columns and len(df_all) > 5:
        recent_price_up = df_all["Gold"].iloc[-1] > df_all["Gold"].iloc[-5]
        recent_gld_down = df_all["GLD"].iloc[-1] < df_all["GLD"].iloc[-5]
        if recent_price_up and recent_gld_down:
            gld_flow_neg = True

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

    # --- Overrides for Sentiment & Capital Flows ---
    extra_alerts = []
    if vix_val > 25 and gold_is_up:
        status_text = "🔥 避险共振强度极高"
        advice_text = "美股恐慌触发黄金避险买盘，建议持有。"
    elif gvz_val > 25 and gold_is_high:
        status_text = "⚠️ 警惕狂热多头踩踏"
        advice_text = "黄金自身波动率 (GVZ) 过高，谨防虚假繁荣后的暴力回调。"
        
    if gld_flow_neg:
        extra_alerts.append("⚠ 筹码背离：金价上涨但主力 ETF 在获利了结，谨防假突破。")
    if cftc_val > 200000:
        extra_alerts.append("🔴 筹码拥挤：投机多头接近历史极值，想买的人已入场，警惕踩踏。")
        
    # Technical Overrides
    current_px = df_all["Gold"].iloc[-1]
    if abs(current_px - pivot_p) < 5:
        extra_alerts.append("⚡ 流动性警报：进入枢轴点真空区，价格波动可能加剧。")
    if current_premium > 15:
        extra_alerts.append("🧧 套利机会：国内溢价过高，警惕机构抛售国内金买入伦敦金。")

    alert_html = "".join([f'<div style="color: #FFD700; font-size: 0.95rem; margin-top: 8px; font-weight: 600;">{a}</div>' for a in extra_alerts])

    st.markdown(f"""
    <div style="background-color: {box_bg}; border-left: 5px solid {box_border}; padding: 20px; border-radius: 10px; border: 1px solid {box_bg.replace('0.15', '0.3')}; margin-bottom: 25px;">
        <h3 style="margin-top: 0px; color: {box_border}; font-size: 1.3rem;">{status_text}</h3>
        <p style="margin-bottom: 5px; font-size: 1.1rem; color: #FFFFFF; line-height: 1.6; font-weight: 500;">
            <b>交易建议：</b>{advice_text}
        </p>
        {alert_html}
        <div style="margin-top: 15px;">
            <a href="https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html" style="color: #BBBBBB; font-size: 0.8rem; text-decoration: none;">🔗 核心来源：CME FedWatch & CFTC Net Position ({fedwatch_prob}%)</a>
        </div>
    </div>
    """, unsafe_allow_html=True)
else:
    st.info("数据加载中，暂无法生成宏观分析...")

# --- Charts ---
st.subheader("📊 核心趋势分析")

# Fig 1: Gold Price + 10Y Real Rate (Dual Axis)
# Add 200MA and Pivot Points
fig1 = make_subplots(specs=[[{"secondary_y": True}]])
fig1.add_trace(
    go.Scatter(x=df_all.index, y=df_all["Gold"], name="金价 (Gold)", line=dict(color="#FFD700", width=3)),
    secondary_y=False,
)

# 200MA Line
if "200MA" in df_all.columns:
    fig1.add_trace(
        go.Scatter(x=df_all.index, y=df_all["200MA"], name="200MA (牛熊线)", line=dict(color="rgba(255, 255, 255, 0.4)", width=2, dash='dot')),
        secondary_y=False,
    )

# Pivot Lines (R1, R2, S1, S2) - Horizontal lines for today
if pivot_p > 0:
    pivot_colors = {"R2": "#FF4B4B", "R1": "#FF4B4B", "P": "#FFFFFF", "S1": "#00CC66", "S2": "#00CC66"}
    for label, level in [("R2", pivot_r2), ("R1", pivot_r1), ("S1", pivot_s1), ("S2", pivot_s2)]:
        fig1.add_hline(y=level, line_dash="dash", line_color=pivot_colors[label], 
                       annotation_text=f"今日 {label}", annotation_position="top right")

fig1.add_trace(
    go.Scatter(x=df_all.index, y=df_all["10Y_Real"], name="10Y 实际利率 (Real Yield)", line=dict(color="#00CCFF", width=2)),
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

st.divider()

# --- Macro Narrative & Sentiment Monitoring Zone ---
with st.container():
    st.markdown("""
        <div style="background-color: #1c1f26; padding: 25px; border-radius: 15px; border: 1px solid #2d3139; margin-bottom: 30px;">
            <h2 style="color: #FFD700; margin-top: 0;">🕸️ 2026 宏观叙事与避险深度监控</h2>
            <p style="color: #FFFFFF !important; font-size: 0.95rem; opacity: 1 !important;">
                分析维度：美元信用摩擦 (Interest/GDP) 与 市场避险情绪溢价 (VIX/GVZ)
            </p>
        </div>
    """, unsafe_allow_html=True)
    
    m_col1, m_col2 = st.columns(2)
    
    with m_col1:
        st.markdown('<p style="color: #ffffff !important; font-weight: bold;">⚖️ 美元信用锚点 (2026 主旋律)</p>', unsafe_allow_html=True)
        if "Interest_to_GDP" in df_all.columns and "DXY" in df_all.columns:
            fig_debt = make_subplots(specs=[[{"secondary_y": True}]])
            fig_debt.add_trace(
                go.Scatter(x=df_all.index, y=df_all["Interest_to_GDP"], name="联邦利息支出(GDP%)", line=dict(color="#FF4B4B", width=3, shape='hv')),
                secondary_y=False,
            )
            fig_debt.add_trace(
                go.Scatter(x=df_all.index, y=df_all["DXY"], name="美元指数 (DXY)", line=dict(color="#FFFFFF", width=2)),
                secondary_y=True,
            )
            fig_debt.update_layout(height=400, template="plotly_dark", margin=dict(l=0,r=0,t=20,b=0), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
            fig_debt.update_yaxes(title_text="利息支出 (%)", secondary_y=False)
            fig_debt.update_yaxes(title_text="DXY 指数", secondary_y=True)
            st.plotly_chart(fig_debt, use_container_width=True)
            st.caption("注：利息支出斜率变陡代表美元信用的“磨损”，是黄金的长线利多。")
        else:
            st.warning("利息支出或 DXY 数据缺失，无法生成信用锚点图。")

    with m_col2:
        st.markdown('<p style="color: #ffffff !important; font-weight: bold;">🌡️ 情绪避险温度计</p>', unsafe_allow_html=True)
        if "VIX" in df_all.columns and "GVZ" in df_all.columns:
            fig_sentiment = go.Figure()
            fig_sentiment.add_trace(go.Scatter(x=df_all.index, y=df_all["VIX"], name="VIX (美股恐慌)", line=dict(color="#FFCC00", width=2)))
            fig_sentiment.add_trace(go.Scatter(x=df_all.index, y=df_all["GVZ"], name="GVZ (黄金波动)", line=dict(color="#00FFAA", width=2, dash='dot')))
            fig_sentiment.update_layout(height=400, template="plotly_dark", margin=dict(l=0,r=0,t=20,b=0), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
            fig_sentiment.update_yaxes(title_text="波动率指数")
            st.plotly_chart(fig_sentiment, use_container_width=True)
            st.caption("注：VIX > 25 常伴随避险买盘，GVZ > 25 需警惕黄金短期过热。")
        else:
            st.warning("VIX 或 GVZ 数据缺失，无法生成情绪温度计。")

st.divider()

# --- Capital Flows & Positions Zone ---
with st.container():
    st.markdown("""
        <div style="background-color: #1c1f26; padding: 25px; border-radius: 15px; border: 1px solid #2d3139; margin-bottom: 30px;">
            <h2 style="color: #FFD700; margin-top: 0;">📦 资金流向与筹码分布</h2>
            <p style="color: #FFFFFF !important; font-size: 0.95rem; opacity: 1 !important;">
                追踪大额资金动向：CFTC 投机头寸 (Smart Money) 与 GLD 持仓变化 (Institutional Flow)
            </p>
        </div>
    """, unsafe_allow_html=True)
    
    f_col1, f_col2 = st.columns(2)
    
    with f_col1:
        st.markdown('<p style="color: #ffffff !important; font-weight: bold;">📊 CFTC 投机净持仓 (Committed Non-Comm)</p>', unsafe_allow_html=True)
        if "CFTC_Net" in df_all.columns:
            # Shift data for visual overlap fix if needed, but primary is Gold
            fig_cftc = make_subplots(specs=[[{"secondary_y": True}]])
            
            # Gold Price
            fig_cftc.add_trace(
                go.Scatter(x=df_all.index, y=df_all["Gold"], name="金价 (Gold)", line=dict(color="#FFD700", width=2)),
                secondary_y=False,
            )
            # CFTC Position (Bar or Line)
            fig_cftc.add_trace(
                go.Scatter(x=df_all.index, y=df_all["CFTC_Net"], name="CFTC 净多头", fill='tozeroy', line=dict(color="#00CCFF", width=1.5)),
                secondary_y=True,
            )
            
            # Crowded Trade Overlay (Rectangle if > 200k)
            latest_cftc = df_all["CFTC_Net"].dropna().iloc[-1]
            if latest_cftc > 200000:
                fig_cftc.add_hrect(y0=200000, y1=max(df_all["CFTC_Net"].max(), 250000), 
                                  fillcolor="rgba(255, 0, 0, 0.1)", borderwidth=0, 
                                  annotation_text="拥挤交易区", annotation_position="top left",
                                  secondary_y=True)

            fig_cftc.update_layout(height=400, template="plotly_dark", margin=dict(l=0,r=0,t=20,b=0), legend=dict(orientation="h", y=1.1))
            fig_cftc.update_yaxes(title_text="Gold Price", secondary_y=False)
            fig_cftc.update_yaxes(title_text="Positions (Contracts)", secondary_y=True)
            st.plotly_chart(fig_cftc, use_container_width=True)
            st.caption("注：净持仓 > 20 万手通常意味着市场过热，谨防多头反向自杀式平仓。")
        else:
            st.warning("CFTC 数据抓取中或暂无更新 (每周五更新)...")

    with f_col2:
        st.markdown('<p style="color: #ffffff !important; font-weight: bold;">📉 GLD 持仓背离分析</p>', unsafe_allow_html=True)
        if "GLD" in df_all.columns:
            fig_gld = make_subplots(specs=[[{"secondary_y": True}]])
            fig_gld.add_trace(
                go.Scatter(x=df_all.index, y=df_all["Gold"], name="金价 (Gold)", line=dict(color="#FFD700", width=2)),
                secondary_y=False,
            )
            fig_gld.add_trace(
                go.Scatter(x=df_all.index, y=df_all["GLD"], name="GLD 持仓 (规模)", line=dict(color="#FFFFFF", width=2, dash='dash')),
                secondary_y=True,
            )
            fig_gld.update_layout(height=400, template="plotly_dark", margin=dict(l=0,r=0,t=20,b=0), legend=dict(orientation="h", y=1.1))
            st.plotly_chart(fig_gld, use_container_width=True)
            st.caption("提示：若金价涨但 GLD 规模降，说明大资金在“且涨且退”，警惕顶部回撤。")
        else:
            st.warning("GLD 数据缺失。")

st.divider()

# --- Technical Execution & Liquidity Zone ---
with st.container():
    st.markdown("""
        <div style="background-color: rgba(0, 255, 170, 0.05); padding: 25px; border-radius: 15px; border: 1px solid #00ffaa33; margin-bottom: 30px;">
            <h2 style="color: #FFD700; margin-top: 0;">🎯 技术面与流动性执行节点</h2>
            <p style="color: #FFFFFF !important; font-size: 0.95rem; opacity: 1 !important;">
                实战执行维度：枢轴点压力支撑、国内外点差套利空间及长期牛熊分界线。
            </p>
        </div>
    """, unsafe_allow_html=True)
    
    t_col1, t_col2 = st.columns(2)
    
    with t_col1:
        st.markdown('<p style="color: #ffffff !important; font-weight: bold;">🏹 今日枢轴点参考 (Pivot Points)</p>', unsafe_allow_html=True)
        if pivot_p > 0:
            st.markdown(f"""
                <div style="background-color: #0e1117; padding: 15px; border-radius: 10px; border: 1px solid #2d3139;">
                    <p style="color: #FF4B4B; margin: 5px 0;"><b>阻力二 (R2):</b> {pivot_r2:.2f}</p>
                    <p style="color: #FFA500; margin: 5px 0;"><b>阻力一 (R1):</b> {pivot_r1:.2f}</p>
                    <p style="color: #FFFFFF; margin: 5px 0; border-top: 1px solid #333; padding-top: 5px;"><b>枢轴中轴 (P):</b> {pivot_p:.2f}</p>
                    <p style="color: #00FFAA; margin: 5px 0;"><b>支撑一 (S1):</b> {pivot_s1:.2f}</p>
                    <p style="color: #00CC66; margin: 5px 0;"><b>支撑二 (S2):</b> {pivot_s2:.2f}</p>
                </div>
            """, unsafe_allow_html=True)
        else:
            st.info("正在计算枢轴点...")

    with t_col2:
        st.markdown('<p style="color: #ffffff !important; font-weight: bold;">💸 国内外点差套利监控</p>', unsafe_allow_html=True)
        st.markdown(f"""
            <div style="background-color: #0e1117; padding: 15px; border-radius: 10px; border: 1px solid #2d3139; height: 100%;">
                <p style="color: #FFFFFF; margin: 5px 0;"><b>实时汇率 (USDCNY):</b> {df_all["USDCNY"].iloc[-1]:.4f}</p>
                <p style="color: #FFFFFF; margin: 5px 0;"><b>伦敦金公允价 (CNY/g):</b> {df_all["Fair_CNY"].iloc[-1]:.2f}</p>
                <h3 style="color: {('#FF4B4B' if current_premium > 15 else '#00FFAA')}; margin: 15px 0 0 0;">
                    国内外溢价: {current_premium:+.2f} CNY/g
                </h3>
                <p style="color: #BBBBBB; font-size: 0.85rem; margin-top: 5px;">
                    {("⚠️ 资金过热，溢价处于高位，建议离场/套利" if current_premium > 15 else "✅ 溢价正常，适合按原计划交易")}
                </p>
            </div>
        """, unsafe_allow_html=True)

# --- Footer ---
st.caption("数据来源: Yahoo Finance (yfinance) & Federal Reserve Economic Data (FRED). 更新时间: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
