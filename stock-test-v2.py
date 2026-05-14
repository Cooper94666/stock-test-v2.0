import streamlit as st
import pandas as pd
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

# =========================
# 基本設定
# =========================
st.set_page_config(page_title="台股全市場動能掃描器", layout="wide")
st.title("🚀 台股全市場動能掃描器（FinMind 全市場版）")

API_TOKEN = st.sidebar.text_input("FinMind API Token", type="password")

limit = st.sidebar.slider("掃描股票數量", 100, 1800, 300)
top_n = st.sidebar.slider("顯示前幾名", 10, 100, 30)

# =========================
# 全市場股票（穩定來源）
# =========================
@st.cache_data(ttl=60*60*24)
def get_stock_list():

    url = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"

    try:
        r = requests.get(url, timeout=15)
        data = r.json()

        stocks = {}

        for item in data:
            code = item.get("公司代號")
            name = item.get("公司簡稱")

            if code and code.isdigit():
                stocks[code] = name

        # 上櫃補充
        url_otc = "https://www.tpex.org.tw/openapi/v1/market/regular_stock/all"
        r2 = requests.get(url_otc, timeout=15)
        data2 = r2.json()

        for item in data2:
            code = item.get("code")
            name = item.get("name")
            if code:
                stocks[code] = name

        return stocks

    except Exception as e:

        st.warning(f"股票清單載入失敗，使用備援：{e}")

        # fallback
        return {
            "2330": "台積電",
            "2317": "鴻海",
            "2454": "聯發科",
            "2303": "聯電",
            "2412": "中華電",
            "2881": "富邦金",
            "2882": "國泰金"
        }

# =========================
# FinMind 抓資料
# =========================
def get_data(stock_id):

    url = "https://api.finmindtrade.com/api/v4/data"

    params = {
        "dataset": "TaiwanStockPrice",
        "data_id": stock_id,
        "start_date": "2024-01-01",
        "token": API_TOKEN
    }

    try:
        r = requests.get(url, params=params, timeout=10)
        js = r.json()

        if "data" not in js:
            return None

        df = pd.DataFrame(js["data"])

        if df.empty:
            return None

        df = df.sort_values("date")
        return df

    except:
        return None

# =========================
# 技術分析
# =========================
def analyze(df):

    close = df["close"].values
    vol = df["Trading_Volume"].values

    def ret(n):
        if len(close) <= n:
            return 0
        return (close[-1] / close[-n] - 1) * 100

    r5 = ret(5)
    r20 = ret(20)

    momentum = r5 * 0.6 + r20 * 0.4

    avg_vol = vol[-20:].mean() if len(vol) >= 20 else vol.mean()

    return r5, r20, avg_vol, momentum

# =========================
# 單檔處理
# =========================
def worker(stock_id, name):

    df = get_data(stock_id)

    if df is None or len(df) < 30:
        return None

    r5, r20, vol, mom = analyze(df)

    return {
        "stock_id": stock_id,
        "name": name,
        "close": df["close"].iloc[-1],
        "return_5d": r5,
        "return_20d": r20,
        "avg_volume": vol,
        "momentum": mom
    }

# =========================
# 主掃描
# =========================
if st.button("🚀 開始全市場掃描", use_container_width=True):

    if not API_TOKEN:
        st.error("請輸入 FinMind Token")
        st.stop()

    stocks = get_stock_list()

    stock_items = list(stocks.items())[:limit]

    st.info(f"掃描股票數量：{len(stock_items)}")

    results = []

    progress = st.progress(0)
    status = st.empty()

    with ThreadPoolExecutor(max_workers=10) as ex:

        futures = {
            ex.submit(worker, sid, name): sid
            for sid, name in stock_items
        }

        for i, f in enumerate(as_completed(futures)):

            res = f.result()

            if res:
                results.append(res)

            progress.progress((i + 1) / len(stock_items))
            status.text(f"{i+1}/{len(stock_items)}")

    df = pd.DataFrame(results)

    if df.empty:
        st.error("沒有資料（請檢查 Token）")
        st.stop()

    df = df.sort_values("momentum", ascending=False)

    show_df = df.head(top_n)

    st.success("掃描完成")

    st.dataframe(show_df, use_container_width=True)

    csv = show_df.to_csv(index=False).encode("utf-8-sig")

    st.download_button(
        "📥 下載CSV",
        csv,
        file_name=f"tw_all_scan_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    )

st.caption("✔ FinMind 全市場動能掃描器")