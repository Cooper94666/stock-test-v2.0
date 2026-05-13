import streamlit as st
import pandas as pd
import requests
import datetime
import time
import urllib3
import json

urllib3.disable_warnings()

# ====================== 頁面設定 ======================
st.set_page_config(
    page_title="台股強勢股掃描器",
    page_icon="📈",
    layout="wide"
)

st.title("📈 台股強勢股掃描器")

# ====================== 取得資料 ======================
@st.cache_data(ttl=300)
def get_all_daily_data():

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
        "Connection": "keep-alive",
    }

    urls = [
        "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL",
        "https://www.twse.com.tw/exchangeReport/STOCK_DAY_ALL?response=json",
    ]

    session = requests.Session()
    session.verify = False

    for url in urls:

        try:
            st.write(f"🔍 嘗試連線：{url}")

            response = session.get(
                url,
                headers=headers,
                timeout=20
            )

            st.write(f"狀態碼：{response.status_code}")

            if response.status_code != 200:
                continue

            if not response.text.strip():
                st.warning("API 回傳空內容")
                continue

            # ======================
            # 第一種 API
            # ======================
            if "openapi" in url:

                try:
                    data = response.json()

                    if isinstance(data, list) and len(data) > 0:
                        df = pd.DataFrame(data)

                        required_cols = [
                            'Code',
                            'Name',
                            'ClosingPrice',
                            'TradeVolume'
                        ]

                        if all(col in df.columns for col in required_cols):
                            return df

                except Exception as e:
                    st.warning(f"JSON 解析失敗: {e}")

            # ======================
            # 第二種 API
            # ======================
            else:

                try:
                    data = response.json()

                    if "data" not in data:
                        continue

                    raw_data = data["data"]
                    fields = data["fields"]

                    df = pd.DataFrame(raw_data, columns=fields)

                    # 欄位重新命名
                    rename_map = {
                        "證券代號": "Code",
                        "證券名稱": "Name",
                        "收盤價": "ClosingPrice",
                        "成交股數": "TradeVolume",
                        "漲跌價差": "Change",
                        "成交金額": "TradeValue",
                    }

                    df = df.rename(columns=rename_map)

                    # 移除逗號
                    for col in df.columns:
                        df[col] = (
                            df[col]
                            .astype(str)
                            .str.replace(",", "")
                        )

                    return df

                except Exception as e:
                    st.warning(f"備援 API 解析失敗: {e}")

        except requests.exceptions.Timeout:
            st.warning("連線逾時")

        except requests.exceptions.ConnectionError:
            st.warning("網路連線失敗")

        except Exception as e:
            st.warning(f"未知錯誤: {e}")

    return None


# ====================== 技術分析 ======================
def technical_check(row):

    try:
        code = str(row['Code'])
        name = str(row.get('Name', ''))

        close = float(row['ClosingPrice'])
        volume = float(row['TradeVolume'])

        change = float(row.get('Change', 0))
        trade_value = float(row.get('TradeValue', 0))

        prev_close = close - change

        if prev_close <= 0:
            change_pct = 0
        else:
            change_pct = (change / prev_close) * 100

        score = 0
        reasons = []

        # ======================
        # 成交量
        # ======================
        if volume > 5_000_000:
            score += 2
            reasons.append("明顯放量")

        elif volume > 1_000_000:
            score += 1
            reasons.append("有放量")

        # ======================
        # 漲幅
        # ======================
        if change_pct > 2:
            score += 3
            reasons.append(f"強漲{change_pct:.2f}%")

        elif change_pct > 1:
            score += 2
            reasons.append(f"上漲{change_pct:.2f}%")

        elif change_pct > 0.5:
            score += 1
            reasons.append(f"微漲{change_pct:.2f}%")

        # ======================
        # 成交金額
        # ======================
        if trade_value > 300_000_000:
            score += 1
            reasons.append("成交金額大")

        # ======================
        # 回傳
        # ======================
        if score >= 3:

            return {
                "stock": code,
                "name": name,
                "score": score,
                "close": round(close, 2),
                "change_pct": round(change_pct, 2),
                "volume_millions": round(volume / 1_000_000, 2),
                "trade_value_billions": round(trade_value / 100_000_000, 2),
                "reasons": "、".join(reasons)
            }

    except:
        return None

    return None


# ====================== 主程式 ======================
if st.button("🔍 開始掃描強勢股", type="primary", use_container_width=True):

    progress = st.progress(0)
    status = st.empty()

    status.text("📡 正在取得台股資料...")

    df = get_all_daily_data()

    if df is None:
        st.error("❌ 無法取得 TWSE 資料")
        st.stop()

    st.success(f"✅ 成功取得 {len(df)} 筆股票資料")

    results = []

    total = len(df)

    for i, (_, row) in enumerate(df.iterrows()):

        if i % 20 == 0:
            progress.progress((i + 1) / total)
            status.text(f"📊 分析中... {i+1}/{total}")

        result = technical_check(row)

        if result:
            results.append(result)

    progress.empty()
    status.empty()

    # ======================
    # 顯示結果
    # ======================
    if len(results) == 0:

        st.warning("⚠️ 沒有找到符合條件的股票")

    else:

        result_df = pd.DataFrame(results)

        result_df = result_df.sort_values(
            by="score",
            ascending=False
        )

        st.success(f"🎉 找到 {len(result_df)} 檔強勢股")

        st.dataframe(
            result_df,
            use_container_width=True,
            height=600
        )

        # 下載 CSV
        csv = result_df.to_csv(
            index=False,
            encoding="utf-8-sig"
        )

        st.download_button(
            "📥 下載 CSV",
            data=csv,
            file_name=f"strong_stock_{datetime.datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )

# ====================== 側邊欄
# ======================
with st.sidebar:

    st.header("📖 評分規則")

    st.markdown("""
    ### 成交量
    - >500萬股：+2
    - >100萬股：+1

    ### 漲幅
    - >2%：+3
    - >1%：+2
    - >0.5%：+1

    ### 成交金額
    - >3億：+1

    ### 總分
    - >=3 分列入強勢股
    """)

st.markdown("---")
st.caption("資料來源：TWSE 台灣證券交易所")