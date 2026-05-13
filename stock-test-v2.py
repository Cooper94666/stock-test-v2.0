import streamlit as st
import pandas as pd
import requests
import datetime
import time
import plotly.graph_objects as go
import plotly.express as px
import urllib3
from datetime import datetime

# ======================
# 關閉 SSL 警告（重要）
# ======================
urllib3.disable_warnings(
    urllib3.exceptions.InsecureRequestWarning
)

# ======================
# 頁面設定
# ======================
st.set_page_config(
    page_title="台股強勢股掃描器",
    page_icon="🔥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ======================
# CSS
# ======================
st.markdown("""
<style>

.stButton > button {
    width: 100%;
    background-color: #ff4b4b;
    color: white;
    font-size: 20px;
    font-weight: bold;
    border-radius: 10px;
}

.stock-card {
    background-color: white;
    padding: 15px;
    border-radius: 10px;
    border-left: 5px solid #ff4b4b;
    margin-bottom: 10px;
}

</style>
""", unsafe_allow_html=True)

# ======================
# 標題
# ======================
st.title("🔥 台股強勢股掃描器")
st.markdown("""
### 即時掃描全市場強勢股
資料來源：TWSE 官方 API
""")

# ======================
# Sidebar
# ======================
with st.sidebar:

    st.header("⚙️ 掃描設定")

    min_volume = st.number_input(
        "最低成交量（股）",
        min_value=100000,
        max_value=50000000,
        value=5000000,
        step=500000
    )

    min_change_pct = st.slider(
        "最低漲幅 (%)",
        min_value=0.0,
        max_value=10.0,
        value=1.0,
        step=0.5
    )

    min_trade_value = st.number_input(
        "最低成交金額（億）",
        min_value=0.5,
        max_value=20.0,
        value=3.0,
        step=0.5
    ) * 100000000

    st.markdown("---")

    st.info("""
### 評分邏輯

- 放量：+1 ~ +2
- 漲幅：+1 ~ +3
- 成交額：+1
- 爆量：+1
- 總分 >= 3 為強勢股
""")

# ======================
# 掃描器
# ======================
class TWSEScanner:

    def __init__(self):

        self.base_url = (
            "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
        )

    # ======================
    # 取得全市場資料
    # ======================
    @st.cache_data(ttl=60)
    def get_all_daily_data(_self):

        try:

            with st.spinner("📡 正在取得全市場資料..."):

                headers = {
                    "User-Agent": (
                        "Mozilla/5.0"
                    )
                }

                resp = requests.get(
                    _self.base_url,
                    timeout=20,
                    verify=False,
                    headers=headers
                )

                resp.raise_for_status()

                data = resp.json()

                df = pd.DataFrame(data)

                # 排除 ETF / 權證
                df = df[
                    df['Code'].astype(str).str.len() == 4
                ]

                return df

        except Exception as e:

            st.error(f"❌ 資料取得失敗: {e}")

            return None

    # ======================
    # 技術分析
    # ======================
    def technical_check(
        self,
        row,
        min_volume,
        min_change_pct,
        min_trade_value
    ):

        try:

            code = str(row.get('Code', ''))
            name = str(row.get('Name', ''))

            # 排除空資料
            if code == '':
                return None

            # ======================
            # 數值解析
            # ======================

            close = float(
                str(row.get('ClosingPrice', '0'))
                .replace(',', '')
            )

            volume = int(
                str(row.get('TradeVolume', '0'))
                .replace(',', '')
            )

            trade_value = int(
                str(row.get('TradeValue', '0'))
                .replace(',', '')
            )

            # 漲跌解析（重要）
            change_raw = str(
                row.get('Change', '0')
            )

            change_raw = (
                change_raw
                .replace('X', '')
                .replace('+', '')
                .replace(',', '')
                .strip()
            )

            try:
                change = float(change_raw)
            except:
                change = 0

            # ======================
            # 前日收盤
            # ======================
            prev_close = close - change

            if prev_close <= 0:
                return None

            # ======================
            # 漲跌幅
            # ======================
            change_pct = (
                change / prev_close * 100
            )

            # ======================
            # 評分
            # ======================
            score = 0

            reasons = []

            # ======================
            # 成交量
            # ======================
            if volume > min_volume * 2:

                score += 2

                reasons.append(
                    f"爆量 {volume/1e6:.1f} 百萬股"
                )

            elif volume > min_volume:

                score += 1

                reasons.append(
                    f"放量 {volume/1e6:.1f} 百萬股"
                )

            # ======================
            # 漲幅
            # ======================
            if change_pct > min_change_pct * 3:

                score += 3

                reasons.append(
                    f"強漲 {change_pct:.2f}%"
                )

            elif change_pct > min_change_pct * 2:

                score += 2

                reasons.append(
                    f"上漲 {change_pct:.2f}%"
                )

            elif change_pct > min_change_pct:

                score += 1

                reasons.append(
                    f"微漲 {change_pct:.2f}%"
                )

            # ======================
            # 成交金額
            # ======================
            if trade_value > min_trade_value:

                score += 1

                reasons.append(
                    f"成交 {trade_value/1e8:.1f} 億"
                )

            # ======================
            # 過濾低價股
            # ======================
            if close < 10:

                score -= 1

            # ======================
            # 最終條件
            # ======================
            if score >= 3:

                return {

                    "stock_id": code,
                    "stock_name": name,

                    "score": score,

                    "close": round(close, 2),

                    "change": round(change, 2),

                    "change_pct": round(change_pct, 2),

                    "volume_million": round(
                        volume / 1e6,
                        2
                    ),

                    "trade_value_billion": round(
                        trade_value / 1e8,
                        2
                    ),

                    "reasons": "、".join(reasons)
                }

            return None

        except:
            return None

    # ======================
    # 全市場掃描
    # ======================
    def scan_stocks(
        self,
        min_volume,
        min_change_pct,
        min_trade_value
    ):

        df = self.get_all_daily_data()

        if df is None:
            return pd.DataFrame()

        results = []

        progress_bar = st.progress(0)

        status = st.empty()

        total = len(df)

        for idx, row in df.iterrows():

            if idx % 50 == 0:

                progress = (
                    idx + 1
                ) / total

                progress_bar.progress(progress)

                status.text(
                    f"掃描進度: {idx+1}/{total}"
                )

            result = self.technical_check(
                row,
                min_volume,
                min_change_pct,
                min_trade_value
            )

            if result:
                results.append(result)

        progress_bar.empty()

        status.empty()

        if len(results) == 0:
            return pd.DataFrame()

        result_df = pd.DataFrame(results)

        result_df = result_df.sort_values(
            'score',
            ascending=False
        )

        return result_df

# ======================
# 圖表
# ======================
def plot_top_stocks(df):

    fig = px.bar(
        df.head(20),
        x='stock_name',
        y='score',
        color='change_pct',
        title='🔥 強勢股排行榜',
        text='score'
    )

    fig.update_layout(
        height=500,
        xaxis_tickangle=-45
    )

    return fig

# ======================
# 主程式
# ======================
def main():

    scan_btn = st.button(
        "🔥 開始掃描強勢股",
        type="primary",
        use_container_width=True
    )

    if scan_btn:

        scanner = TWSEScanner()

        with st.spinner("掃描中..."):

            result_df = scanner.scan_stocks(
                min_volume,
                min_change_pct,
                min_trade_value
            )

        # ======================
        # 顯示結果
        # ======================
        if result_df.empty:

            st.warning(
                "⚠️ 沒有符合條件股票"
            )

        else:

            st.success(
                f"✅ 找到 {len(result_df)} 檔強勢股"
            )

            # ======================
            # 統計
            # ======================
            col1, col2, col3, col4 = st.columns(4)

            with col1:
                st.metric(
                    "強勢股數",
                    len(result_df)
                )

            with col2:
                st.metric(
                    "平均漲幅",
                    f"{result_df['change_pct'].mean():.2f}%"
                )

            with col3:
                st.metric(
                    "平均分數",
                    f"{result_df['score'].mean():.1f}"
                )

            with col4:
                st.metric(
                    "最高分",
                    result_df['score'].max()
                )

            # ======================
            # 圖表
            # ======================
            fig = plot_top_stocks(result_df)

            st.plotly_chart(
                fig,
                use_container_width=True
            )

            # ======================
            # DataFrame
            # ======================
            display_df = result_df.copy()

            display_df.columns = [

                '代碼',
                '名稱',
                '技術分數',
                '收盤價',
                '漲跌點',
                '漲跌幅%',
                '成交量(百萬股)',
                '成交金額(億)',
                '強勢原因'
            ]

            st.subheader("📋 強勢股列表")

            st.dataframe(
                display_df,
                use_container_width=True,
                height=600
            )

            # ======================
            # Top10 卡片
            # ======================
            st.subheader("🏆 Top 10 強勢股")

            for _, row in result_df.head(10).iterrows():

                st.markdown(f"""
                <div class="stock-card">

                <h4>
                {row['stock_id']} - {row['stock_name']}
                </h4>

                <p>
                ⭐ 分數: <b>{row['score']}</b>
                </p>

                <p>
                📈 漲幅:
                <span style="color:red">
                {row['change_pct']}%
                </span>
                </p>

                <p>
                💡 {row['reasons']}
                </p>

                </div>
                """, unsafe_allow_html=True)

            # ======================
            # CSV下載
            # ======================
            csv = display_df.to_csv(
                index=False
            ).encode('utf-8-sig')

            st.download_button(
                label="📥 下載CSV",
                data=csv,
                file_name=f"""
strong_stocks_
{datetime.now().strftime('%Y%m%d_%H%M')}.csv
""",
                mime='text/csv'
            )

# ======================
# 執行
# ======================
if __name__ == "__main__":

    main()