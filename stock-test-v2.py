import streamlit as st
import pandas as pd
import requests
import datetime
import time
import json
import os
import urllib3

# 禁用 SSL 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ====================== 頁面設定 ======================
st.set_page_config(
    page_title="台股強勢股掃描器",
    page_icon="🔥",
    layout="wide"
)

st.title("🔥 台股強勢股掃描器")
st.markdown("**按下按鈕掃描全市場技術面強勢股票**")

# ====================== 取得全市場最新日線資料 ======================
def get_all_daily_data():
    """從 TWSE 官方 API 一次取得所有股票的最新交易日資料"""
    url = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
    try:
        # 使用 session 並忽略 SSL 驗證
        session = requests.Session()
        session.verify = False
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
        resp = session.get(url, timeout=15)
        data = resp.json()
        
        df = pd.DataFrame(data)
        return df
    except Exception as e:
        st.error(f"❌ TWSE API 失敗: {e}")
        return None

# ====================== 技術分析 ======================
def technical_check(row):
    try:
        code = row['Code']
        name = row.get('Name', '')
        close = float(row['ClosingPrice'])
        volume = int(row['TradeVolume'])
        change = float(row.get('Change', 0))
        prev_close = close - change
        change_pct = (change / prev_close * 100) if prev_close > 0 else 0
        
        score = 0
        reasons = []

        # 放量條件（成交股數）
        if volume > 5_000_000:  # 500萬股以上
            score += 2
            reasons.append("明顯放量")
        elif volume > 1_000_000:
            score += 1
            reasons.append("有放量")

        # 漲幅條件
        if change_pct > 2.0:
            score += 3
            reasons.append(f"強漲{change_pct:.2f}%")
        elif change_pct > 1.0:
            score += 2
            reasons.append(f"上漲{change_pct:.2f}%")
        elif change_pct > 0.5:
            score += 1
            reasons.append(f"微漲{change_pct:.2f}%")

        # 成交金額（單位：元）
        trade_value = int(row.get('TradeValue', 0))
        if trade_value > 300_000_000:  # 3億以上
            score += 1
            reasons.append("成交金額大")

        if score >= 3:
            return {
                "stock": code,
                "name": name,
                "score": score,
                "close": round(close, 2),
                "change_pct": round(change_pct, 2),
                "volume_millions": round(volume / 1_000_000, 1),
                "trade_value_billions": round(trade_value / 100_000_000, 1),
                "reasons": "、".join(reasons)
            }
        return None
    except Exception as e:
        return None

# ====================== 主程式 ======================
# 建立按鈕
if st.button("🔍 開始掃描強勢股", type="primary", use_container_width=True):
    
    # 顯示進度
    progress_text = st.empty()
    progress_bar = st.progress(0)
    
    # 獲取資料
    progress_text.text("📡 正在從 TWSE 官方取得全市場日線資料...")
    df = get_all_daily_data()
    
    if df is None:
        st.error("無法取得資料，請檢查網路連線")
        st.stop()
    
    st.success(f"✅ 成功取得 {len(df)} 檔股票的最新日線資料")
    
    # 開始分析
    progress_text.text(f"🚀 開始分析 {len(df)} 檔股票...")
    
    results = []
    
    for i, (idx, row) in enumerate(df.iterrows()):
        # 更新進度
        if i % 10 == 0:
            progress = (i + 1) / len(df)
            progress_bar.progress(progress)
            progress_text.text(f"📊 分析進度: {i+1}/{len(df)} ({progress*100:.1f}%)")
        
        # 分析股票
        result = technical_check(row)
        if result:
            results.append(result)
    
    # 清除進度顯示
    progress_text.empty()
    progress_bar.empty()
    
    # 顯示結果
    if results:
        st.balloons()
        st.success(f"🎉 掃描完成！共找到 {len(results)} 檔強勢股")
        
        # 轉換為 DataFrame
        df_result = pd.DataFrame(results)
        df_result = df_result.sort_values("score", ascending=False).reset_index(drop=True)
        
        # 顯示統計摘要
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("📊 強勢股總數", len(df_result))
        with col2:
            st.metric("⭐ 平均技術分數", f"{df_result['score'].mean():.1f}")
        with col3:
            st.metric("📈 平均漲幅", f"{df_result['change_pct'].mean():.2f}%")
        with col4:
            st.metric("🏆 最高分數", f"{df_result['score'].max()}")
        
        # 顯示前20強勢股
        st.subheader("🔥 強勢股清單 (前20名)")
        
        # 準備顯示的資料
        display_df = df_result.head(20).copy()
        display_df.index = range(1, len(display_df) + 1)
        display_df.columns = ['代碼', '名稱', '技術分數', '收盤價', '漲跌幅%', 
                            '成交量(萬張)', '成交金額(億)', '強勢理由']
        
        # 設定欄位格式
        column_config = {
            "技術分數": st.column_config.NumberColumn(format="%d"),
            "漲跌幅%": st.column_config.NumberColumn(format="%.2f%%"),
            "成交量(萬張)": st.column_config.NumberColumn(format="%.1f"),
            "成交金額(億)": st.column_config.NumberColumn(format="%.1f"),
        }
        
        st.dataframe(display_df, use_container_width=True, height=400, column_config=column_config)
        
        # 顯示詳細卡片（前10名）
        st.subheader("🏆 前10強強勢股詳細資訊")
        
        for idx, row in df_result.head(10).iterrows():
            with st.container():
                col1, col2, col3, col4, col5 = st.columns([1, 2, 1, 1, 1])
                
                # 根據漲幅決定顏色
                color = "#ff4b4b" if row['change_pct'] > 0 else "#00a65a"
                
                with col1:
                    st.markdown(f"### #{idx+1}")
                with col2:
                    st.markdown(f"### {row['stock']} - {row['name']}")
                with col3:
                    st.markdown(f"**技術分數:** `{row['score']}`")
                with col4:
                    st.markdown(f"**收盤價:** `{row['close']}`")
                with col5:
                    st.markdown(f"**漲跌幅:** <span style='color:{color};font-size:20px;font-weight:bold;'>{row['change_pct']:+.2f}%</span>", unsafe_allow_html=True)
                
                col1, col2, col3 = st.columns([1, 1, 1])
                with col1:
                    st.metric("成交量", f"{row['volume_millions']}萬張")
                with col2:
                    st.metric("成交金額", f"{row['trade_value_billions']}億")
                with col3:
                    st.markdown(f"**強勢理由:** {row['reasons']}")
                
                st.divider()
        
        # 下載功能
        csv = df_result.to_csv(index=False, encoding='utf-8-sig')
        st.download_button(
            label="📥 下載完整強勢股清單 (CSV)",
            data=csv,
            file_name=f"strong_stocks_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
        )
        
    else:
        st.warning("⚠️ 本次沒有找到符合條件的股票，請放寬條件後再試試看")

# 側邊欄說明
with st.sidebar:
    st.header("📖 評分標準")
    st.markdown("""
    **放量條件：**
    - 明顯放量 (>500萬股)：+2分
    - 有放量 (>100萬股)：+1分
    
    **漲幅條件：**
    - 強漲 (>2%)：+3分
    - 上漲 (>1%)：+2分
    - 微漲 (>0.5%)：+1分
    
    **成交金額：**
    - 成交金額大 (>3億)：+1分
    
    **總分 ≥ 3分** 即為強勢股
    """)
    
    st.markdown("---")
    st.caption("資料來源：TWSE 台灣證券交易所")
    st.caption(f"最後更新：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

st.markdown("---")
st.caption("⚠️ 免責聲明：本工具僅供參考，所有數據來自公開資訊，投資決策請自行判斷")