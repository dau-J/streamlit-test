import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import matplotlib.pyplot as plt
from datetime import date

# 데이터 불러오기 (미리 다운로드 받은 CSV 사용)
@st.cache_data
def load_data():
    df = pd.read_csv("seoul_air_quality.csv")  # 이 파일은 미리 다운받아야 함
    df['측정일시'] = pd.to_datetime(df['측정일시'])
    return df

df = load_data()

# ---------------------------
# 위젯: 자치구 선택 + 날짜 선택
# ---------------------------
st.title("서울시 대기오염 분석 웹앱 🌫️")

districts = df['자치구'].unique()
selected_gu = st.selectbox("자치구를 선택하세요", sorted(districts))
selected_date = st.date_input("날짜를 선택하세요", value=date(2024, 5, 1))

# ---------------------------
# 데이터 필터링
# ---------------------------
filtered = df[
    (df['자치구'] == selected_gu) &
    (df['측정일시'].dt.date == selected_date)
]

# ---------------------------
# 차트 출력
# ---------------------------
st.subheader(f"{selected_gu}의 {selected_date} 미세먼지(PM10) 변화 그래프")
if not filtered.empty:
    fig, ax = plt.subplots()
    ax.plot(filtered['측정일시'].dt.hour, filtered['PM10'], marker='o')
    ax.set_xlabel("시간")
    ax.set_ylabel("PM10 (㎍/m³)")
    ax.set_title(f"{selected_gu}의 시간대별 PM10 농도")
    st.pyplot(fig)
else:
    st.warning("해당 날짜의 데이터가 없습니다.")

# ---------------------------
# 지도 출력
# ---------------------------
st.subheader(f"{selected_gu}의 대기오염 지도 시각화")

if not filtered.empty:
    lat = filtered.iloc[0]['위도']
    lon = filtered.iloc[0]['경도']
    pm10 = filtered['PM10'].mean()

    map_ = folium.Map(location=[lat, lon], zoom_start=12)
    folium.CircleMarker(
        location=[lat, lon],
        radius=15,
        color="red" if pm10 > 80 else "orange" if pm10 > 30 else "green",
        fill=True,
        fill_opacity=0.7,
        popup=f"{selected_gu}\nPM10 평균: {pm10:.1f}"
    ).add_to(map_)

    st_folium(map_, width=700, height=450)
else:
    st.warning("지도를 표시할 데이터가 없습니다.")
