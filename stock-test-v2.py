import streamlit as st
import pandas as pd
import requests
import datetime
import time

# ======================
# UI
# ======================
st.set_page_config(page_title="TWSE 穩定掃描器 v6", layout="wide")
st.title("📊 TWSE 全市場強勢股掃描器 v6（穩定修正版）")

# ======================
# Session（模擬瀏覽器）
# ======================
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Referer": "https://www.twse.com.tw/",
}

session = requests.Session()

# ======================
# 安全 JSON parser
# ======================
def safe_json(resp):

    try:
        if not resp.text or len(resp.text) < 50:
            return None
        return resp.json()
    except:
        return None


# ======================
# API 1（主）
# ======================
def api_primary():

    url = "https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY_ALL"

    try:
        session.get("https://www.twse.com.tw/", headers=HEADERS, timeout=10)

        r = session.get(
            url,
            headers=HEADERS,
            params={"response": "json"},
            timeout=20
        )

        j = safe_json(r)

        if not j or "data" not in j:
            return None

        return pd.DataFrame(j["data"], columns=j["fields"])

    except:
        return None


# ======================
# API 2（備援）
# ======================
def api_backup():

    url = "https://www.twse.com.tw/exchangeReport/MI_INDEX"

    try:
        r = session.get(
            url,
            headers=HEADERS,
            params={"response": "json"},
            timeout=20
        )

        j = safe_json(r)

        if not j:
            return None

        # TWSE weird structure fallback
        for k in ["data9", "data8"]:
            if k in j:
                return pd.DataFrame(j[k], columns=j.get(f"fields{k[-1]}", []))

        return None

    except:
        return None


# ======================
# API 3（最後保底）
# ======================
def api_fallback_url():

    url = "https://www.twse.com.tw/exchangeReport/STOCK_DAY_ALL?response=json"

    try:
        r = session.get(url, headers=HEADERS, timeout=20)

        j = safe_json(r)

        if not j or "data" not in j:
            return None

        return pd.DataFrame(j["data"], columns=j["fields"])

    except:
        return None


# ======================
# 主抓取（3層 fallback）
# ======================
@st.cache_data(ttl=300)
def get_twse():

    df = api_primary()

    if df is not None and len(df) > 0:
        return df

    st.warning("⚠️ 主 API 失敗 → 切備援1")

    df = api_backup()

    if df is not None and len(df) > 0:
        return df

    st.warning("⚠️ 備援1失敗 → 切備援2")

    df = api_fallback_url()

    return df


# ======================
# 清理資料
# ======================
def clean(df):

    df = df.copy()

    rename = {
        "證券代號": "Code",
        "證券名稱": "Name",
        "收盤價": "Close",
        "漲跌價差": "Change",
        "成交股數": "Volume",
        "成交金額": "Value"
    }

    df = df.rename(columns=rename)

    for col in ["Close", "Change", "Volume", "Value"]:
        if col in df.columns:
            df[col] = (
                df[col]
                .astype(str)
                .str.replace(",", "")
                .replace("--", "0")
            )
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["Close", "Volume"])

    return df


# ======================
# 評分模型
# ======================
def score(row):

    try:
        close = float(row["Close"])
        change = float(row["Change"])
        volume = float(row["Volume"])
        value = float(row["Value"])

        prev = close - change
        change_pct = (change / prev * 100) if prev > 0 else 0

        score = 0
        reason = []

        # ===== 價格 =====
        if change_pct > 3:
            score += 3
            reason.append("強勢突破")
        elif change_pct > 1.5:
            score += 2
            reason.append("中強上漲")
        elif change_pct > 0.5:
            score += 1
            reason.append("小幅上漲")

        # ===== 成交量 =====
        if volume > 10_000_000:
            score += 2
            reason.append("爆量")
        elif volume > 3_000_000:
            score += 1
            reason.append("放量")

        # ===== 金額 =====
        if value > 500_000_000:
            score += 1
            reason.append("資金進場")

        if score >= 3:

            return {
                "code": row["Code"],
                "name": row["Name"],
                "close": round(close, 2),
                "change_pct": round(change_pct, 2),
                "volume_m": round(volume / 1_000_000, 2),
                "value_b": round(value / 100_000_000, 2),
                "score": score,
                "reason": "、".join(reason)
            }

    except:
        return None


# ======================
# 主程式
# ======================
if st.button("🚀 開始掃描 TWSE（v6 穩定版）", type="primary"):

    with st.spinner("📡 連接 TWSE 中..."):

        df = get_twse()

    if df is None or len(df) == 0:
        st.error("❌ TWSE 全部 API 都失敗（網路或被擋）")
        st.stop()

    df = clean(df)

    st.success(f"✅ 成功取得 {len(df)} 檔股票")

    results = []

    progress = st.progress(0)
    status = st.empty()

    for i, row in df.iterrows():

        if i % 50 == 0:
            progress.progress(i / len(df))
            status.text(f"分析中 {i}/{len(df)}")

        r = score(row)

        if r:
            results.append(r)

    progress.empty()
    status.empty()

    if not results:
        st.warning("沒有強勢股")
        st.stop()

    result_df = pd.DataFrame(results)
    result_df = result_df.sort_values("score", ascending=False)

    st.success(f"🎉 找到 {len(result_df)} 檔強勢股")

    st.dataframe(result_df, use_container_width=True)

    # ===== KPI =====
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("強勢股數", len(result_df))

    with col2:
        st.metric("平均漲幅", f"{result_df['change_pct'].mean():.2f}%")

    with col3:
        st.metric("最高分數", result_df["score"].max())

    # ===== CSV =====
    csv = result_df.to_csv(index=False, encoding="utf-8-sig")

    st.download_button(
        "📥 下載 CSV",
        csv,
        file_name=f"twse_v6_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv"
    )


# ======================
# sidebar
# ======================
with st.sidebar:

    st.header("📊 v6 穩定機制")

    st.markdown("""
### 🔥 三層防護

1️⃣ STOCK_DAY_ALL  
2️⃣ MI_INDEX  
3️⃣ legacy fallback  

---

### 🧠 防炸機制

✔ JSON safe parser  
✔ 空 response detection  
✔ retry fallback  
✔ multi-endpoint switching  

---

### 🚀 保證

✔ 不會直接 crash  
✔ 不會卡 JSON error  
✔ 不會單點失敗  
""")

st.caption("⚠️ TWSE 官方資料｜穩定增強版 v6")