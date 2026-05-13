import streamlit as st
import pandas as pd
import requests
import datetime
import time
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import json

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
        font-size: 20px;
        font-weight: bold;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 15px;
        border-radius: 10px;
        text-align: center;
    }
    .stock-card {
        background-color: #ffffff;
        padding: 10px;
        border-radius: 8px;
        border-left: 4px solid #ff4b4b;
        margin: 5px 0;
    }
</style>
""", unsafe_allow_html=True)

# ====================== 標題區域 ======================
st.title("🔥 台股強勢股掃描器")
st.markdown("**即時掃描全市場技術面強勢股票 | 資料來源：TWSE 官方 API**")

# ====================== 側邊欄設定 ======================
with st.sidebar:
    st.header("⚙️ 掃描設定")
    
    # 技術面參數
    st.subheader("📊 技術面條件")
    min_volume = st.number_input(
        "最低成交量（股）",
        min_value=100000,
        max_value=10000000,
        value=5000000,
        step=500000,
        help="成交股數需大於此值"
    )
    
    min_change_pct = st.slider(
        "最低漲幅（%）",
        min_value=0.0,
        max_value=5.0,
        value=1.0,
        step=0.5,
        help="股價漲跌幅需大於此值"
    )
    
    min_trade_value = st.number_input(
        "最低成交金額（億）",
        min_value=0.5,
        max_value=10.0,
        value=3.0,
        step=0.5,
        help="成交金額需大於此值（單位：億）"
    ) * 100000000
    
    # 進階設定
    st.subheader("🔧 進階設定")
    save_progress = st.checkbox("儲存掃描進度", value=True)
    show_all_results = st.checkbox("顯示所有結果", value=True)
    
    st.markdown("---")
    st.info("""
    **評分標準**：
    - ⭐ 放量：+1~2分
    - ⭐ 漲幅：+1~3分  
    - ⭐ 成交大：+1分
    - **總分 ≥ 3分** 即為強勢股
    """)

# ====================== 主要功能類別 ======================
class TWSE_Scanner:
    def __init__(self):
        self.base_url = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
        
    def get_all_daily_data(self):
        """從 TWSE 官方 API 取得所有股票最新日線資料"""
        try:
            with st.spinner("📡 正在從 TWSE 官方取得全市場資料..."):
                resp = requests.get(self.base_url, timeout=15)
                data = resp.json()
                df = pd.DataFrame(data)
                return df
        except Exception as e:
            st.error(f"❌ 資料取得失敗: {e}")
            return None
    
    def technical_check(self, row, min_volume, min_change_pct, min_trade_value):
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
            
            # 成交量條件
            if volume > min_volume:
                score += 2
                reasons.append(f"放量 ({volume/1e6:.1f}萬張)")
            elif volume > min_volume * 0.5:
                score += 1
                reasons.append(f"微幅放量 ({volume/1e6:.1f}萬張)")
            
            # 漲幅條件
            if change_pct > min_change_pct * 2:
                score += 3
                reasons.append(f"強漲 {change_pct:.2f}%")
            elif change_pct > min_change_pct:
                score += 2
                reasons.append(f"上漲 {change_pct:.2f}%")
            elif change_pct > 0:
                score += 1
                reasons.append(f"微漲 {change_pct:.2f}%")
            
            # 成交金額條件
            if trade_value > min_trade_value:
                score += 1
                reasons.append(f"成交 {trade_value/1e8:.1f}億")
            elif trade_value > min_trade_value * 0.5:
                reasons.append(f"成交 {trade_value/1e8:.1f}億")
            
            # 總分篩選
            if score >= 3:
                return {
                    "stock_id": code,
                    "stock_name": name,
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
    
    def scan_stocks(self, min_volume, min_change_pct, min_trade_value, save_progress=True):
        """掃描所有股票"""
        # 獲取資料
        df = self.get_all_daily_data()
        if df is None:
            return pd.DataFrame()
        
        # 顯示掃描資訊
        st.info(f"📊 共 {len(df)} 檔股票待掃描")
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        results = []
        
        for idx, row in df.iterrows():
            # 更新進度
            if idx % 50 == 0:
                progress = (idx + 1) / len(df)
                progress_bar.progress(progress)
                status_text.text(f"掃描進度: {idx+1}/{len(df)} ({progress*100:.1f}%)")
            
            # 分析股票
            result = self.technical_check(row, min_volume, min_change_pct, min_trade_value)
            if result:
                results.append(result)
            
            # 稍微延遲避免請求過快
            if idx % 100 == 0:
                time.sleep(0.1)
        
        # 清除進度條
        progress_bar.empty()
        status_text.empty()
        
        if results:
            df_result = pd.DataFrame(results)
            df_result = df_result.sort_values("score", ascending=False)
            return df_result
        
        return pd.DataFrame()

# ====================== 圖表繪製函數 ======================
def plot_top_stocks(df, top_n=20):
    """繪製前N名強勢股長條圖"""
    fig = px.bar(
        df.head(top_n),
        x='stock_name',
        y='score',
        color='score',
        color_continuous_scale='RdYlGn',
        title=f"🔥 前{top_n}強強勢股評分排名",
        labels={'stock_name': '股票名稱', 'score': '技術面總分'}
    )
    fig.update_layout(height=500, xaxis_tickangle=-45)
    return fig

def plot_return_distribution(df):
    """繪製漲跌幅分布圖"""
    fig = px.histogram(
        df,
        x='change_pct',
        nbins=20,
        title="📈 強勢股漲跌幅分布",
        labels={'change_pct': '漲跌幅 (%)', 'count': '股票檔數'},
        color_discrete_sequence=['#ff4b4b']
    )
    fig.update_layout(height=400)
    return fig

def create_stock_card(row):
    """創建股票卡片"""
    return f"""
    <div class="stock-card">
        <h4>{row['stock_id']} - {row['stock_name']}</h4>
        <table style="width:100%">
            <tr>
                <td>📊 技術分數: <b>{row['score']}</b></td>
                <td>💰 收盤價: <b>{row['close']}</b></td>
            </tr>
            <tr>
                <td>📈 漲幅: <b style="color:#ff4b4b">{row['change_pct']}%</b></td>
                <td>📊 成交量: <b>{row['volume_millions']}萬張</b></td>
            </tr>
            <tr>
                <td colspan="2">💡 {row['reasons']}</td>
            </tr>
        </table>
    </div>
    """

# ====================== 個股詳細資訊函數 ======================
def show_stock_detail(stock_id, stock_name):
    """顯示個股詳細資訊和K線圖"""
    st.subheader(f"📈 {stock_id} - {stock_name} 詳細分析")
    
    # 這裡可以加入更多個股分析功能
    # 例如：歷史K線、技術指標等
    
    st.info("個股詳細分析功能開發中...")

# ====================== 主程式 ======================
def main():
    # 掃描按鈕
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        scan_button = st.button("🔥 開始掃描強勢股", type="primary", use_container_width=True)
    
    if scan_button:
        # 建立掃描器
        scanner = TWSE_Scanner()
        
        # 執行掃描
        with st.spinner("掃描中，請稍候..."):
            df_results = scanner.scan_stocks(
                min_volume=min_volume,
                min_change_pct=min_change_pct,
                min_trade_value=min_trade_value,
                save_progress=save_progress
            )
        
        if not df_results.empty:
            # 顯示統計摘要
            st.success(f"✅ 掃描完成！共找到 {len(df_results)} 檔強勢股")
            
            # 統計卡片
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("📊 強勢股總數", len(df_results))
            with col2:
                st.metric("⭐ 平均技術分數", f"{df_results['score'].mean():.1f}")
            with col3:
                st.metric("📈 平均漲幅", f"{df_results['change_pct'].mean():.2f}%")
            with col4:
                st.metric("🏆 最高分數", f"{df_results['score'].max()}")
            
            # 圖表區域
            st.subheader("📊 數據視覺化")
            tab1, tab2 = st.tabs(["📊 排名圖表", "📈 漲幅分布"])
            
            with tab1:
                fig1 = plot_top_stocks(df_results, min(20, len(df_results)))
                st.plotly_chart(fig1, use_container_width=True)
            
            with tab2:
                fig2 = plot_return_distribution(df_results)
                st.plotly_chart(fig2, use_container_width=True)
            
            # 結果顯示模式
            if show_all_results:
                st.subheader("📋 完整強勢股清單")
                
                # 準備顯示資料
                display_df = df_results.copy()
                display_df.columns = ['代碼', '名稱', '技術分數', '收盤價', '漲跌幅%', 
                                    '成交量(萬張)', '成交金額(億)', '強勢理由', '漲跌點數']
                
                # 使用st.dataframe顯示
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
            else:
                # 卡片模式顯示前10名
                st.subheader("🏆 前10強強勢股")
                cols = st.columns(2)
                for idx, row in df_results.head(10).iterrows():
                    with cols[idx % 2]:
                        st.markdown(create_stock_card(row), unsafe_allow_html=True)
            
            # 個股查詢
            st.subheader("🔍 個股查詢")
            selected_stock = st.selectbox(
                "選擇股票查看詳細資訊",
                options=df_results['stock_id'].tolist(),
                format_func=lambda x: f"{x} - {df_results[df_results['stock_id']==x]['stock_name'].iloc[0]}"
            )
            
            if selected_stock:
                stock_detail = df_results[df_results['stock_id'] == selected_stock].iloc[0]
                
                # 顯示詳細資訊
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("技術分數", stock_detail['score'])
                with col2:
                    st.metric("收盤價", f"{stock_detail['close']}")
                with col3:
                    st.metric("漲跌幅", f"{stock_detail['change_pct']}%", 
                             delta=f"{stock_detail['change_pct']}%" if stock_detail['change_pct'] > 0 else None)
                with col4:
                    st.metric("成交量", f"{stock_detail['volume_millions']}萬張")
                
                st.info(f"💡 強勢理由：{stock_detail['reasons']}")
        
        else:
            st.warning("⚠️ 未找到符合條件的強勢股，請放寬篩選條件後再試試看")

# ====================== 執行 ======================
if __name__ == "__main__":
    main()