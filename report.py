import streamlit as st
import pandas as pd
import altair as alt
import geopandas as gpd
from streamlit_folium import st_folium
import folium
import openrouteservice
import os
from dotenv import load_dotenv

load_dotenv()

# openrouteservice Directions API 호출을 캐싱
@st.cache_data(show_spinner=False)
def get_route_from_ors(route_points, api_key):
    import openrouteservice
    # 소수점 6자리로 제한, tuple로 변환하여 캐시 입력값 안정화
    route_points = tuple((round(x, 6), round(y, 6)) for x, y in route_points)
    client = openrouteservice.Client(key=api_key)
    return client.directions(
        coordinates=route_points,
        profile='driving-car',
        format='geojson'
    )

# 부산 버스 승하차 데이터 불러오기
@st.cache_data
def load_data():
    df = pd.read_csv('부산광역시_버스노선별 승하차 정보.csv', encoding='cp949')
    return df

df = load_data()

st.title('부산광역시 버스노선별 승하차 정보 분석')

# Input Widget 1: 노선번호 선택
route_options = df['노선번호'].unique()
route = st.selectbox('노선번호를 선택하세요', route_options)

# Input Widget 2: 정류장명 검색
stop_search = st.text_input('정류장명(일부 입력 가능)')

# Input Widget 3: 정류장순서 슬라이더
min_order = int(df[df['노선번호'] == route]['정류장순서'].min())
max_order = int(df[df['노선번호'] == route]['정류장순서'].max())
order_range = st.slider('정류장순서 범위', min_order, max_order, (min_order, max_order))

# 필터링
df_filtered = df[df['노선번호'] == route]
if stop_search:
    df_filtered = df_filtered[df_filtered['정류장명'].str.contains(stop_search)]
df_filtered = df_filtered[(df_filtered['정류장순서'] >= order_range[0]) & (df_filtered['정류장순서'] <= order_range[1])]

st.write(f"선택된 노선: {route}")
st.write(f"정류장명 검색: {stop_search}")
st.write(f"정류장순서 범위: {order_range[0]} ~ {order_range[1]}")

# Chart 1: 정류장별 승차/하차 합계 Bar Chart
if not df_filtered.empty:
    chart_data = df_filtered[['정류장명', '승차합계', '하차합계']].melt(id_vars='정류장명', var_name='유형', value_name='합계')
    bar_chart = alt.Chart(chart_data).mark_bar().encode(
        x=alt.X('정류장명:N', sort='-y'),
        y='합계:Q',
        color='유형:N',
        tooltip=['정류장명', '유형', '합계']
    ).properties(width=700, height=400, title='정류장별 승차/하차 합계')
    st.altair_chart(bar_chart, use_container_width=True)
else:
    st.warning('해당 조건에 맞는 정류장이 없습니다.')

# Chart 2: 시간대별 승차합계 Line Chart (일부 시간대만 예시)
time_cols = [col for col in df.columns if '승차건수' in col and '합계' not in col]
time_sum = df_filtered[time_cols].sum().reset_index()
time_sum.columns = ['시간대', '승차합계']
time_sum['시간대'] = time_sum['시간대'].str.replace('_승차건수\(선탑_후탑\)', '', regex=True)
line_chart = alt.Chart(time_sum).mark_line(point=True).encode(
    x=alt.X('시간대', sort=None),
    y='승차합계',
    tooltip=['시간대', '승차합계']
).properties(width=700, height=300, title='시간대별 승차합계')
st.altair_chart(line_chart, use_container_width=True)

# 정류장 위치 데이터 불러오기 (Shapefile)
station_gdf = gpd.read_file('tl_bus_station_info.shp', encoding='utf-8')
# 좌표계가 WGS84가 아니면 변환
if station_gdf.crs and station_gdf.crs.to_string() != 'EPSG:4326':
    station_gdf = station_gdf.to_crs(epsg=4326)
# 정류장명, 위도, 경도 컬럼명만 맞추기 (geometry에서 추출 X)
station_gdf = station_gdf.rename(columns={'bstopnm': '정류장명', 'gpsy': '위도', 'gpsx': '경도'})
# 정류장명 전처리(소문자, 공백제거)
station_gdf['정류장명'] = station_gdf['정류장명'].str.strip().str.lower()
df['정류장명'] = df['정류장명'].str.strip().str.lower()
# 부산 지역 위도/경도 범위로 이상치 필터링
station_gdf = station_gdf[(station_gdf['위도'] > 34) & (station_gdf['위도'] < 36) & (station_gdf['경도'] > 128) & (station_gdf['경도'] < 130)]

# 승하차 데이터와 정류장 위치 병합
# (df_filtered 생성 이후에 정류장명 전처리 필요)
df_filtered['정류장명'] = df_filtered['정류장명'].str.strip().str.lower()
df_map = pd.merge(df_filtered, station_gdf[['정류장명', '위도', '경도']], on='정류장명', how='inner')

# 지도 시각화 (folium)
if not df_map.empty:
    m = folium.Map(location=[df_map['위도'].mean(), df_map['경도'].mean()], zoom_start=13)
    # openrouteservice 클라이언트 생성 (API키는 환경변수에서 읽음)
    ors_api_key = os.environ.get('ORS_API_KEY')
    if not ors_api_key:
        st.error('openrouteservice API 키가 환경변수 ORS_API_KEY에 설정되어 있지 않습니다.')
    else:
        ors_client = openrouteservice.Client(key=ors_api_key)
        # 정류장 경로를 순서대로 실제 도로 경로로 연결
        MAX_WAYPOINTS = 70
        route_points = df_map.sort_values('정류장순서')[['경도', '위도']].values.tolist()
        if len(route_points) > MAX_WAYPOINTS:
            st.warning(f"경로 탐색은 최대 {MAX_WAYPOINTS}개의 정류장까지만 지원합니다. 처음 70개만 경로로 연결됩니다.")
            route_points = route_points[:MAX_WAYPOINTS]
        if len(route_points) >= 2:
            try:
                route = get_route_from_ors(route_points, ors_api_key)
                folium.GeoJson(route, name='route', style_function=lambda x: {'color': 'red', 'weight': 4, 'opacity': 0.7}).add_to(m)
            except Exception as e:
                st.warning(f'경로 탐색 중 오류 발생: {e}')
    for _, row in df_map.iterrows():
        folium.CircleMarker(
            location=[row['위도'], row['경도']],
            radius=5 + row['승차합계'] / 20,  # 승차합계에 따라 크기 조절
            color='blue',
            fill=True,
            fill_opacity=0.7,
            popup=f"정류장명: {row['정류장명']}<br>승차합계: {row['승차합계']}<br>하차합계: {row['하차합계']}"
        ).add_to(m)
    st.subheader('정류장 위치 및 실제 도로 경로(GIS)')
    st_folium(m, width=700, height=500)
else:
    st.info('선택된 조건에 해당하는 정류장 위치 데이터가 없습니다.')
