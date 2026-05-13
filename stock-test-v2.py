import streamlit as st
import pandas as pd
import json
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

# ======================
# UI
# ======================
st.set_page_config(page_title="TWSE Selenium Cloud版", layout="wide")
st.title("📊 TWSE Selenium（Streamlit Cloud 可用版）")

# ======================
# 建立 Chrome（Cloud safe）
# ======================
def create_driver():

    options = Options()

    # 🔥 Streamlit Cloud 必備
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")

    # 🔥 讓 Cloud 更穩
    options.add_argument("--disable-blink-features=AutomationControlled")

    # Streamlit Cloud 內建 chromedriver
    driver = webdriver.Chrome(options=options)

    return driver


# ======================
# 抓 TWSE
# ======================
def fetch_twse():

    driver = create_driver()

    try:
        url = "https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY_ALL?response=json"

        driver.get(url)

        time.sleep(3)

        text = driver.find_element(By.TAG_NAME, "pre").text

        data = json.loads(text)

        driver.quit()

        if "data" not in data:
            return None

        df = pd.DataFrame(data["data"], columns=data["fields"])

        return df

    except Exception as e:

        driver.quit()
        st.error(f"Selenium error: {e}")
        return None


# ======================
# 清理
# ======================
def clean(df):

    df = df.copy()

    df = df.rename(columns={
        "證券代號": "Code",
        "證券名稱": "Name",
        "收盤價": "Close",
        "漲跌價差": "Change",
        "成交股數": "Volume",
        "成交金額": "Value"
    })

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
# scoring
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

        if change_pct > 3:
            score += 3
            reason.append("強勢突破")
        elif change_pct > 1.5:
            score += 2
            reason.append("中強上漲")
        elif change_pct > 0.5:
            score += 1
            reason.append("小漲")

        if volume > 10_000_000:
            score += 2
            reason.append("爆量")
        elif volume > 3_000_000:
            score += 1
            reason.append("放量")

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
if st.button("🚀 開始掃描 TWSE（Cloud Selenium）", type="primary"):

    with st.spinner("🌐 Selenium 抓取 TWSE 中..."):

        df = fetch_twse()

    if df is None:
        st.error("❌ 無法取得 TWSE 資料")
        st.stop()

    df = clean(df)

    st.success(f"✅ 取得 {len(df)} 檔股票")

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

    csv = result_df.to_csv(index=False, encoding="utf-8-sig")

    st.download_button(
        "📥 下載 CSV",
        csv,
        file_name="twse_cloud_selenium.csv",
        mime="text/csv"
    )


# ======================
# sidebar
# ======================
with st.sidebar:

    st.header("☁️ Cloud Selenium版")

    st.markdown("""
### ✔ 特點
- Streamlit Cloud 可跑
- headless Chrome
- 不用 webdriver-manager
- 不怕 TWSE API 擋

---

### ⚠️ 注意
- 首次載入較慢
- Cloud 可能有資源限制
- 建議掃描 ≤ 1000 檔
""")

st.caption("⚠️ Selenium + Streamlit Cloud 版本")