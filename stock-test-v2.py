import streamlit as st
import pandas as pd
import requests
import datetime
import time

# ======================
# 頁面
# ======================
st.set_page_config(page_title="TWSE v3 全市場掃描器", layout="wide")
st.title("📊 TWSE v3 全市場強勢股掃描器")

# ======================
# TWSE 全市場資料
# ======================
@st.cache_data(ttl=300)
def get_twse_all():

    url = "https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY_ALL"

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://www.twse.com.tw/",
    }

    params = {
        "date": "",
        "response": "json"
    }

    session = requests.Session()

    for i in range(3):  # 🔥 retry

        try:
            resp = session.get(
                url,
                headers=headers,
                params=params,
                timeout=20
            )

            if not resp.text.strip():
                continue

            data = resp.json()

            if "data" not in data:
                continue

            df = pd.DataFrame(data["data"], columns=data["fields"])

            return df

        except Exception as e:
            st.warning(f"TWSE retry {i+1}/3 failed")

            time.sleep(1)

    return None


# ======================
# 資料清洗
# ======================
def clean_df(df):

    df = df.copy()

    # 欄位轉換
    rename_map = {
        "證券代號": "Code",
        "證券名稱": "Name",
        "收盤價": "Close",
        "漲跌價差": "Change",
        "成交股數": "Volume",
        "成交金額": "Value"
    }

    df = df.rename(columns=rename_map)

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
# 技術分析核心
# ======================
def score_stock(row):

    try:
        close = float(row["Close"])
        change = float(row["Change"])
        volume = float(row["Volume"])
        value = float(row["Value"])

        prev = close - change

        change_pct = (change / prev * 100) if prev > 0 else 0

        score = 0
        reasons = []

        # ======================
        # 漲幅動能
        # ======================
        if change_pct > 3:
            score += 3
            reasons.append("強勢突破")

        elif change_pct > 1.5:
            score += 2
            reasons.append("中強上漲")

        elif change_pct > 0.5:
            score += 1
            reasons.append("小漲動能")

        # ======================
        # 成交量（市場相對）
        # ======================
        if volume > 10_000_000:
            score += 2
            reasons.append("爆量")

        elif volume > 3_000_000:
            score += 1
            reasons.append("放量")

        # ======================
        # 成交金額
        # ======================
        if value > 500_000_000:
            score += 1
            reasons.append("資金進場")

        if score >= 3:

            return {
                "code": row["Code"],
                "name": row["Name"],
                "close": round(close, 2),
                "change_pct": round(change_pct, 2),
                "volume_m": round(volume / 1_000_000, 2),
                "value_b": round(value / 100_000_000, 2),
                "score": score,
                "reason": "、".join(reasons)
            }

    except:
        return None


# ======================
# 主程式
# ======================
if st.button("🚀 開始掃描 TWSE 全市場", type="primary"):

    with st.spinner("📡 正在抓取 TWSE 全市場資料..."):

        df = get_twse_all()

    if df is None:
        st.error("❌ TWSE API 無回應")
        st.stop()

    df = clean_df(df)

    st.success(f"✅ 成功取得 {len(df)} 檔股票")

    results = []

    progress = st.progress(0)
    status = st.empty()

    for i, row in df.iterrows():

        if i % 50 == 0:
            progress.progress(i / len(df))
            status.text(f"分析中 {i}/{len(df)}")

        r = score_stock(row)

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

    # ======================
    # KPI
    # ======================
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("強勢股數量", len(result_df))

    with col2:
        st.metric("平均漲幅", f"{result_df['change_pct'].mean():.2f}%")

    with col3:
        st.metric("最高分數", result_df["score"].max())

    # ======================
    # CSV
    # ======================
    csv = result_df.to_csv(index=False, encoding="utf-8-sig")

    st.download_button(
        "📥 下載結果",
        csv,
        file_name=f"twse_v3_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv"
    )


# ======================
# 側邊欄
# ======================
with st.sidebar:

    st.header("📊 v3 模型")

    st.markdown("""
### 🔥 三大因子模型

#### 📈 價格動能
- >3% 強突破
- >1.5% 中強
- >0.5% 動能

#### 📊 量能
- >1000萬股 爆量
- >300萬股 放量

#### 💰 資金
- >5億成交金額

---

### 🧠 v3 升級點
✔ 全市場掃描  
✔ TWSE 官方 API  
✔ retry 機制  
✔ 清洗 NaN / "--"  
✔ 動能模型  
✔ 可擴展成量化策略  
""")

st.caption("⚠️ 僅供研究，不構成投資建議")