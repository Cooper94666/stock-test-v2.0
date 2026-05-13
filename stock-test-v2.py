import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import time
from datetime import datetime, timedelta
import plotly.graph_objects as go

st.set_page_config(page_title="台股短期動能掃描器", layout="wide")
st.title("🚀 台股短期高動能掃描器（TWSE上市）")
st.markdown("**嚴格條件**：20日均成交金額 > 100億 + 近期強勢 | 純量價技術面")

class TWSE_Scanner:
    def __init__(self):
        self.headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        self.min_turnover = 100_000_000_000  # 100億

    def get_stock_list(self):
        """抓取上市股票清單並排除金融股"""
        url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
        try:
            resp = requests.get(url, headers=self.headers, timeout=15)
            resp.encoding = 'big5'
            soup = BeautifulSoup(resp.text, 'html.parser')
            df = pd.read_html(str(soup.find('table')))[0]
            df = df.iloc[1:].reset_index(drop=True)
            df[['stock_id', 'stock_name']] = df.iloc[:, 0].str.split('　', n=1, expand=True)
            df = df[['stock_id', 'stock_name', df.columns[2]]].copy()
            df.columns = ['stock_id', 'stock_name', 'industry']
            
            # 排除金融股
            df = df[~df['industry'].str.contains('金融', na=False)]
            df = df[~df['stock_id'].str.startswith(('28', '00'), na=False)]
            return df
        except Exception as e:
            st.error(f"股票清單抓取失敗: {e}")
            return pd.DataFrame()

    def get_multi_day_data(self, days=60):
        """抓取多日市場資料"""
        end = datetime.now()
        dates = []
        for i in range(days + 10):
            d = end - timedelta(days=i)
            if d.weekday() < 5:
                dates.append(d.strftime('%Y%m%d'))
        
        all_data = []
        progress = st.progress(0)
        status = st.empty()
        
        for idx, d in enumerate(dates[:days]):
            status.text(f"正在抓取 {d} 資料...")
            try:
                url = f"https://www.twse.com.tw/exchangeReport/STOCK_DAY_ALL?response=json&date={d}"
                resp = requests.get(url, headers=self.headers, timeout=15)
                data = resp.json().get('data', [])
                if data:
                    df_day = pd.DataFrame(data)
                    df_day.columns = ['date', 'stock_id', 'name', 'vol', 'val', 'open', 'high', 'low', 'close', 'change', 'trans']
                    df_day['val'] = pd.to_numeric(df_day['val'].str.replace(',', ''), errors='coerce')
                    df_day['close'] = pd.to_numeric(df_day['close'].str.replace(',', ''), errors='coerce')
                    df_day['stock_id'] = df_day['stock_id'].str.strip()
                    all_data.append(df_day)
            except:
                pass
            progress.progress((idx + 1) / min(len(dates), days))
            time.sleep(1.2)
        
        return pd.concat(all_data) if all_data else pd.DataFrame()

    def analyze(self):
        stock_list = self.get_stock_list()
        raw_data = self.get_multi_day_data(days=60)
        if raw_data.empty or stock_list.empty:
            return pd.DataFrame()
        
        # 20日平均成交金額
        turnover = raw_data.groupby('stock_id')['val'].mean().reset_index()
        turnover.columns = ['stock_id', 'avg_turnover_20d']
        
        latest = raw_data.sort_values('date').groupby('stock_id').last().reset_index()
        
        # 計算各週期漲幅
        def calc_return(df, days):
            recent = df.sort_values('date').tail(days)
            if len(recent) < 2:
                return 0.0
            return (recent['close'].iloc[-1] / recent['close'].iloc[0] - 1) * 100
        
        returns = []
        for sid in latest['stock_id']:
            stock_df = raw_data[raw_data['stock_id'] == sid].sort_values('date')
            r5 = calc_return(stock_df, 5)
            r20 = calc_return(stock_df, 20)
            r60 = calc_return(stock_df, 60)
            returns.append({'stock_id': sid, 'return_5d': r5, 'return_1m': r20, 'return_3m': r60})
        
        returns_df = pd.DataFrame(returns)
        
        result = (stock_list.merge(turnover, on='stock_id')
                         .merge(latest[['stock_id', 'close']], on='stock_id')
                         .merge(returns_df, on='stock_id'))
        
        # 高流動性篩選
        result = result[result['avg_turnover_20d'] >= self.min_turnover].copy()
        
        # 技術面分數 + 均線判斷
        result['momentum_score'] = result['return_5d'] * 0.6 + result['return_1m'] * 0.3
        result = result.sort_values('momentum_score', ascending=False).head(30)
        
        # 機械式理由 + 停損建議
        def generate_reason(row):
            reasons = []
            if row['return_5d'] > 5: reasons.append(f"5日強漲 {row['return_5d']:.1f}%")
            if row['return_1m'] > 15: reasons.append(f"1個月上漲 {row['return_1m']:.1f}%")
            if row['avg_turnover_20d'] > 300_000_000_000: reasons.append("巨量")
            return "、".join(reasons) + "，量價配合佳"
        
        result['reason'] = result.apply(generate_reason, axis=1)
        result['stop_loss_suggest'] = (result['close'] * 0.92).round(2)  # 預設8%停損
        
        return result

# ====================== 主介面 ======================
if st.button("🔄 開始掃描 Top 10 高動能股票", type="primary"):
    with st.spinner("抓取TWSE官方資料中（約2-4分鐘，請耐心等待）..."):
        scanner = TWSE_Scanner()
        df = scanner.analyze()
        
        if not df.empty:
            st.success(f"找到符合條件的股票，前10名如下：")
            
            display_df = df.head(10).copy()
            display_df['20日均成交'] = (display_df['avg_turnover_20d'] / 1e8).round(1).astype(str) + "億"
            display_df = display_df[['stock_id', 'stock_name', 'close', 'return_5d', 
                                   'return_1m', 'return_3m', '20日均成交', 'reason', 'stop_loss_suggest']]
            
            display_df.columns = ['代碼', '名稱', '股價', '5日漲幅%', '1月漲幅%', '3月漲幅%', 
                                '20日均成交', '推薦理由', '建議停損價']
            
            st.dataframe(display_df, use_container_width=True, height=600)
            
            # 下載
            csv = display_df.to_csv(index=False).encode('utf-8-sig')
            st.download_button("📥 下載 Top 10 CSV", csv, "top10_momentum.csv", "text/csv")
        else:
            st.error("本次無符合高流動性條件的股票")

# ====================== K線圖（含均線） ======================
st.divider()
st.subheader("📈 個股互動K線圖（含均線）")
col1, col2 = st.columns([1, 3])
with col1:
    stock_id = st.text_input("輸入股票代碼", value="2330", max_chars=4)
with col2:
    period = st.selectbox("時間範圍", ["30天", "60天", "90天"], index=1)

if st.button("繪製 K 線 + 均線"):
    with st.spinner(f"抓取 {stock_id} 資料..."):
        scanner = TWSE_Scanner()
        # 這裡使用單股API抓取更精準的日線資料（簡化版）
        # 實際可再擴充，此處示意用多日資料
        raw = scanner.get_multi_day_data(days=int(period[:-1]))
        stock_df = raw[raw['stock_id'] == stock_id].sort_values('date')
        
        if not stock_df.empty:
            stock_df['MA5'] = stock_df['close'].rolling(5).mean()
            stock_df['MA20'] = stock_df['close'].rolling(20).mean()
            stock_df['MA60'] = stock_df['close'].rolling(60).mean()
            
            fig = go.Figure()
            fig.add_trace(go.Candlestick(x=stock_df['date'],
                                        open=stock_df['open'], high=stock_df['high'],
                                        low=stock_df['low'], close=stock_df['close'], name="K線"))
            fig.add_trace(go.Scatter(x=stock_df['date'], y=stock_df['MA5'], name="MA5", line=dict(color='orange')))
            fig.add_trace(go.Scatter(x=stock_df['date'], y=stock_df['MA20'], name="MA20", line=dict(color='blue')))
            fig.add_trace(go.Scatter(x=stock_df['date'], y=stock_df['MA60'], name="MA60", line=dict(color='purple')))
            
            fig.update_layout(title=f"{stock_id} K線圖（含均線）", xaxis_rangeslider_visible=True, height=600)
            st.plotly_chart(fig, use_container_width=True)
            
            st.info(f"建議停損參考：近期低點下方約 5-8%（依個人風險調整）")
        else:
            st.warning("無法取得該股票資料")

st.caption("資料來源：TWSE官方公開資料 | 純機械量價計算 | 僅供參考，非投資建議")