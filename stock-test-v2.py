import streamlit as st
import pandas as pd
import requests
import datetime
import time
import json
import os
import urllib3
from datetime import datetime, timedelta
import plotly.graph_objects as go
import plotly.express as px

# 禁用 SSL 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ====================== 頁面設定 ======================
st.set_page_config(
    page_title="台股強勢股掃描器",
    page_icon="🔥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ====================== 自訂 CSS ======================
st.markdown("""
<style>
    .stButton > button {
        width: 100%;
        background-color: #ff4b4b;
        color: white;
        font-size: 18px;
        font-weight: bold;
        border-radius: 8px;
        padding: 10px;
    }
    .stButton > button:hover {
        background-color: #ff6b6b;
        transform: translateY(-2px);
        transition: all 0.3s;
    }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 20px;
        border-radius: 15px;
        color: white;
        text-align: center;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .stock-card {
        background-color: white;
        padding: 15px;
        border-radius: 12px;
        border-left: 4px solid #ff4b4b;
        margin: 10px 0;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        transition: transform 0.2s;
    }
    .stock-card:hover {
        transform: translateX(5px);
    }
    .score-badge {
        background-color: #ff4b4b;
        color: white;
        padding: 5px 12px;
        border-radius: 20px;
        font-weight: bold;
        display: inline-block;
    }
    .reasons-text {
        color: #666;
        font-size: 14px;
        margin-top: 8px;
    }
    .big-number {
        font-size: 36px;
        font-weight: bold;
    }
    .info-box {
        background-color: #f0f2f6;
        padding: 15px;
        border-radius: 10px;
        margin: 10px 0;
    }
</style>
""", unsafe_allow_html=True)

# ====================== 標題區域 ======================
col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    st.title("🔥 台股強勢股掃描器")
    st.markdown("<p style='text-align: center'>即時掃描全市場技術面強勢股票 | 資料來源：TWSE 官方 API</p>", unsafe_allow_html=True)

# ====================== 側邊欄設定 ======================
with st.sidebar:
    st.header("⚙️ 掃描設定")
    
    # 使用說明
    with st.expander("📖 使用說明", expanded=False):
        st.markdown("""
        **操作步驟**：
        1. 調整掃描參數
        2. 點擊「開始掃描」
        3. 等待掃描完成
        4. 查看強勢股清單
        
        **評分標準**：
        - 明顯放量 (>500萬股)：+2分
        - 有放量 (>100萬股)：+1分
        - 強漲 (>2%)：+3分
        - 上漲 (>1%)：+2分
        - 微漲 (>0.5%)：+1分
        - 成交金額大 (>3億)：+1分
        
        **總分 ≥ 3分** 即為強勢股
        """)
    
    st.markdown("---")
    
    # 技術面參數
    st.subheader("📊 篩選條件")
    
    min_volume = st.number_input(
        "最低成交量（股）",
        min_value=100000,
        max_value=10000000,
        value=5000000,
        step=500000,
        help="成交股數需大於此值才會獲得放量分數",
        format="%d"
    )
    
    min_change_pct = st.slider(
        "最低漲幅門檻（%）",
        min_value=0.0,
        max_value=5.0,
        value=1.0,
        step=0.5,
        help="漲幅超過此值才會獲得漲幅分數"
    )
    
    min_trade_value = st.number_input(
        "最低成交金額門檻（億）",
        min_value=0.5,
        max_value=10.0,
        value=3.0,
        step=0.5,
        help="成交金額需大於此值才會獲得加分"
    ) * 100000000
    
    st.markdown("---")
    
    # 進階設定
    st.subheader("🔧 進階設定")
    
    save_progress = st.checkbox("儲存掃描進度", value=True, help="中斷後可從上次進度繼續")
    show_all = st.checkbox("顯示所有結果", value=True, help="顯示完整清單或僅顯示前20名")
    enable_cache = st.checkbox("啟用資料快取", value=True, help="快取當日資料，避免重複抓取")
    
    st.markdown("---")
    
    # 狀態顯示
    st.subheader("📊 掃描狀態")
    status_placeholder = st.empty()

# ====================== 快取功能 ======================
@st.cache_data(ttl=3600)  # 快取1小時
def get_cached_data():
    """快取的資料獲取函數"""
    session = requests.Session()
    session.verify = False
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    })
    
    try:
        # 使用 HTTP 而非 HTTPS 避免 SSL 問題
        url = "http://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
        resp = session.get(url, timeout=15)
        data = resp.json()
        df = pd.DataFrame(data)
        return df
    except Exception as e:
        # 備用方案：使用 HTTPS 但忽略驗證
        try:
            url = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
            resp = session.get(url, timeout=15, verify=False)
            data = resp.json()
            df = pd.DataFrame(data)
            return df
        except Exception as e2:
            st.error(f"資料獲取失敗: {e2}")
            return None

# ====================== 取得全市場最新日線資料 ======================
def get_all_daily_data(use_cache=True):
    """從 TWSE 官方 API 一次取得所有股票的最新交易日資料"""
    if use_cache:
        df = get_cached_data()
        if df is not None:
            return df
    
    # 不使用快取時直接抓取
    session = requests.Session()
    session.verify = False
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    })
    
    try:
        status_placeholder.info("📡 正在從 TWSE 官方取得全市場日線資料...")
        url = "http://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
        resp = session.get(url, timeout=15)
        data = resp.json()
        df = pd.DataFrame(data)
        status_placeholder.success(f"✅ 成功取得 {len(df)} 檔股票的最新日線資料")
        return df
    except Exception as e:
        status_placeholder.error(f"❌ TWSE API 失敗: {e}")
        return None

# ====================== 技術分析 ======================
def technical_check(row, min_volume, min_change_pct, min_trade_value):
    """技術面分析單一股票"""
    try:
        code = row.get('Code', '')
        name = row.get('Name', '')
        
        # 轉換數值
        close = float(row.get('ClosingPrice', 0))
        volume = int(row.get('TradeVolume', 0))
        trade_value = int(row.get('TradeValue', 0))
        change = float(row.get('Change', 0))
        
        # 計算漲跌幅
        prev_close = close - change
        change_pct = (change / prev_close * 100) if prev_close > 0 else 0
        
        # 評分計算
        score = 0
        reasons = []
        
        # 放量條件
        if volume > min_volume:
            score += 2
            reasons.append(f"明顯放量 ({volume/1e6:.1f}萬張)")
        elif volume > min_volume * 0.2:
            score += 1
            reasons.append(f"有放量 ({volume/1e6:.1f}萬張)")
        
        # 漲幅條件
        if change_pct > min_change_pct * 2:
            score += 3
            reasons.append(f"強漲 {change_pct:.2f}%")
        elif change_pct > min_change_pct:
            score += 2
            reasons.append(f"上漲 {change_pct:.2f}%")
        elif change_pct > min_change_pct * 0.5:
            score += 1
            reasons.append(f"微漲 {change_pct:.2f}%")
        
        # 成交金額條件
        if trade_value > min_trade_value:
            score += 1
            reasons.append(f"成交金額大 ({trade_value/1e8:.1f}億)")
        
        # 總分篩選
        if score >= 3:
            return {
                "stock": code,
                "name": name,
                "score": score,
                "close": round(close, 2),
                "change_pct": round(change_pct, 2),
                "volume_millions": round(volume / 1e6, 1),
                "trade_value_billions": round(trade_value / 1e8, 1),
                "reasons": "、".join(reasons),
                "change": round(change, 2)
            }
        return None
    except Exception as e:
        return None

# ====================== 進度存取 ======================
PROGRESS_FILE = "scan_progress.json"

def save_progress(completed_idx, results):
    """儲存掃描進度"""
    if not save_progress:
        return
    try:
        with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "completed_idx": completed_idx,
                "results": results,
                "last_update": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }, f, ensure_ascii=False, indent=2)
    except:
        pass

def load_progress():
    """載入掃描進度"""
    if not save_progress:
        return 0, []
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("completed_idx", 0), data.get("results", [])
        except:
            pass
    return 0, []

# ====================== 圖表繪製函數 ======================
def plot_top_stocks(df, top_n=20):
    """繪製前N名強勢股長條圖"""
    fig = px.bar(
        df.head(top_n),
        x='name',
        y='score',
        color='score',
        color_continuous_scale='RdYlGn',
        title=f"🔥 前{top_n}強強勢股評分排名",
        labels={'name': '股票名稱', 'score': '技術面總分', 'change_pct': '漲跌幅(%)'}
    )
    fig.update_layout(
        height=500,
        xaxis_tickangle=-45,
        showlegend=True,
        hovermode='x unified'
    )
    fig.update_traces(
        text=df.head(top_n)['change_pct'].apply(lambda x: f'{x:+.1f}%'),
        textposition='outside'
    )
    return fig

def plot_score_distribution(df):
    """繪製分數分布圖"""
    fig = px.histogram(
        df,
        x='score',
        nbins=10,
        title="📊 強勢股技術分數分布",
        labels={'score': '技術分數', 'count': '股票檔數'},
        color_discrete_sequence=['#ff4b4b']
    )
    fig.update_layout(height=400)
    return fig

def create_stock_card(row, rank):
    """創建股票卡片"""
    color = "#ff4b4b" if row['change_pct'] > 0 else "#00a65a"
    return f"""
    <div class="stock-card">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
            <div>
                <span class="score-badge">🏆 第{rank}名</span>
                <span style="margin-left: 10px; font-size: 18px; font-weight: bold;">{row['stock']} - {row['name']}</span>
            </div>
            <span style="font-size: 28px; font-weight: bold; color: {color};">{row['change_pct']:+.1f}%</span>
        </div>
        <div style="display: flex; justify-content: space-around; margin: 15px 0;">
            <div style="text-align: center;">
                <div style="font-size: 12px; color: #999;">技術分數</div>
                <div style="font-size: 24px; font-weight: bold;">{row['score']}</div>
            </div>
            <div style="text-align: center;">
                <div style="font-size: 12px; color: #999;">收盤價</div>
                <div style="font-size: 20px; font-weight: bold;">{row['close']}</div>
            </div>
            <div style="text-align: center;">
                <div style="font-size: 12px; color: #999;">成交量</div>
                <div style="font-size: 16px;">{row['volume_millions']}萬張</div>
            </div>
            <div style="text-align: center;">
                <div style="font-size: 12px; color: #999;">成交金額</div>
                <div style="font-size: 16px;">{row['trade_value_billions']}億</div>
            </div>
        </div>
        <div class="reasons-text">
            💡 {row['reasons']}
        </div>
    </div>
    """

# ====================== 主流程 ======================
def main():
    # 掃描按鈕
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        start_scan = st.button("🔍 開始掃描強勢股", type="primary", use_container_width=True)
    
    if start_scan:
        # 載入進度
        start_idx, results = load_progress()
        
        # 獲取資料
        df = get_all_daily_data(use_cache=enable_cache)
        
        if df is None:
            st.error("無法取得資料，請檢查網路連線後重試")
            return
        
        # 顯示掃描資訊
        st.info(f"📊 共 {len(df)} 檔股票待掃描")
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # 建立結果容器
        result_container = st.container()
        
        # 開始掃描
        for i in range(start_idx, len(df)):
            # 更新進度
            if i % 10 == 0:
                progress = (i + 1) / len(df)
                progress_bar.progress(progress)
                status_text.text(f"掃描進度: {i+1}/{len(df)} ({progress*100:.1f}%)")
            
            # 分析股票
            row = df.iloc[i]
            result = technical_check(row, min_volume, min_change_pct, min_trade_value)
            
            if result:
                results.append(result)
                # 即時顯示找到的強勢股
                with result_container:
                    st.success(f"✅ 找到強勢股: {result['stock']} - {result['name']} (評分: {result['score']})")
            
            # 定期儲存進度
            if save_progress and (i + 1) % 50 == 0:
                save_progress(i + 1, results)
        
        # 清除進度條
        progress_bar.empty()
        status_text.empty()
        
        # 儲存最終結果
        if save_progress:
            save_progress(len(df), results)
        
        # 顯示結果
        if results:
            st.balloons()
            st.success(f"🎉 掃描完成！共找到 {len(results)} 檔強勢股")
            
            # 轉換為 DataFrame
            df_results = pd.DataFrame(results)
            df_results = df_results.sort_values("score", ascending=False).reset_index(drop=True)
            
            # 統計卡片
            col1, col2, col3, col4, col5 = st.columns(5)
            with col1:
                st.metric("📊 強勢股總數", len(df_results))
            with col2:
                st.metric("⭐ 平均技術分數", f"{df_results['score'].mean():.1f}")
            with col3:
                st.metric("📈 平均漲幅", f"{df_results['change_pct'].mean():.2f}%")
            with col4:
                st.metric("🏆 最高分數", f"{df_results['score'].max()}")
            with col5:
                st.metric("🚀 最大漲幅", f"{df_results['change_pct'].max():.2f}%")
            
            # 圖表區域
            st.subheader("📊 數據視覺化")
            tab1, tab2 = st.tabs(["📊 強勢股排名", "📈 分數分布"])
            
            with tab1:
                fig1 = plot_top_stocks(df_results, min(20, len(df_results)))
                st.plotly_chart(fig1, use_container_width=True)
            
            with tab2:
                fig2 = plot_score_distribution(df_results)
                st.plotly_chart(fig2, use_container_width=True)
            
            # 強勢股卡片展示（前10名）
            st.subheader("🏆 強勢股排行榜（前10名）")
            
            cols = st.columns(2)
            for idx, (_, row) in enumerate(df_results.head(10).iterrows()):
                with cols[idx % 2]:
                    st.markdown(create_stock_card(row, idx+1), unsafe_allow_html=True)
            
            # 完整清單
            if show_all:
                with st.expander("📋 查看完整強勢股清單"):
                    display_df = df_results.copy()
                    display_df.columns = ['代碼', '名稱', '技術分數', '收盤價', '漲跌幅%', 
                                        '成交量(萬張)', '成交金額(億)', '強勢理由', '漲跌點數']
                    
                    st.dataframe(
                        display_df,
                        use_container_width=True,
                        height=400,
                        column_config={
                            "技術分數": st.column_config.NumberColumn(format="%d"),
                            "漲跌幅%": st.column_config.NumberColumn(format="%.2f%%"),
                            "成交量(萬張)": st.column_config.NumberColumn(format="%.1f"),
                            "成交金額(億)": st.column_config.NumberColumn(format="%.1f"),
                        }
                    )
                    
                    # 下載功能
                    csv = display_df.to_csv(index=False).encode('utf-8-sig')
                    st.download_button(
                        label="📥 下載強勢股清單 (CSV)",
                        data=csv,
                        file_name=f"strong_stocks_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                        mime="text/csv",
                    )
            
            # 清除進度檔案
            if save_progress and os.path.exists(PROGRESS_FILE):
                os.remove(PROGRESS_FILE)
                st.info("🗑️ 已清除掃描進度記錄")
        
        else:
            st.warning("⚠️ 未找到符合條件的強勢股，請放寬篩選條件後再試試看")

# ====================== 執行 ======================
if __name__ == "__main__":
    main()