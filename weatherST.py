import os
import time
from typing import Dict, Any, List

import requests
import pandas as pd
import streamlit as st

# ----------------------------
# 한글 -> 영문 도시 맵 (부족하면 아래 dict에 계속 추가)
# ----------------------------
CITY_MAP: Dict[str, str] = {
    "서울": "Seoul",
    "세종": "Sejong",
    "부산": "Busan",
    "대구": "Daegu",
    "인천": "Incheon",
    "광주": "Gwangju",
    "대전": "Daejeon",
    "울산": "Ulsan",
    "수원": "Suwon",
    "춘천": "Chuncheon",
    "청주": "Cheongju",
    "홍성": "Hongseong",
    "전주": "Jeonju",
    "무안": "Muan",
    "안동": "Andong",
    "창원": "Changwon",
    "제주": "Jeju",
}

GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# ----------------------------
# Streamlit 기본 설정
# ----------------------------
st.set_page_config(page_title="K-Weather (Open-Meteo)", page_icon="🌤", layout="wide")

st.title("🌤 K-Weather (Open-Meteo + Streamlit)")
st.caption("한글 도시명을 입력하면 자동으로 영문명으로 변환해 날씨를 보여줘요. (API Key 불필요)")


# ----------------------------
# 유틸: 캐시된 API 호출
# ----------------------------
@st.cache_data(ttl=10 * 60, show_spinner=False)
def geocode_city(korean_name: str) -> Dict[str, Any]:
    """한글명 -> 영문명 변환 후 지오코딩 결과(위경도) 반환"""
    eng_name = CITY_MAP.get(korean_name)
    if not eng_name:
        raise ValueError(f"'{korean_name}'은(는) 아직 지원 목록에 없습니다. 상단 도시 선택 또는 입력을 바꿔보세요.")

    params = {
        "name": eng_name,
        "count": 1,
        "language": "ko",
        "country_code": "KR",
        "format": "json",
    }
    r = requests.get(GEO_URL, params=params, timeout=20)
    r.raise_for_status()
    data = r.json()
    if not data.get("results"):
        raise ValueError(f"지오코딩 실패: {korean_name} ({eng_name})")
    top = data["results"][0]
    return {
        "name_kr": korean_name,
        "name_en": eng_name,
        "lat": top["latitude"],
        "lon": top["longitude"],
        "admin1": top.get("admin1"),
        "country": top.get("country"),
    }


@st.cache_data(ttl=5 * 60, show_spinner=False)
def fetch_forecast(
    lat: float,
    lon: float,
    hourly: List[str] = None,
    daily: List[str] = None,
    current: List[str] = None,
    forecast_days: int = 7,
    timezone: str = "Asia/Seoul",
) -> Dict[str, Any]:
    """Open-Meteo 예보 호출"""
    hourly = hourly or ["temperature_2m", "relative_humidity_2m", "precipitation", "weather_code", "wind_speed_10m"]
    daily = daily or ["temperature_2m_max", "temperature_2m_min", "precipitation_sum", "sunrise", "sunset"]
    current = current or ["temperature_2m", "relative_humidity_2m", "apparent_temperature", "precipitation", "weather_code", "wind_speed_10m"]
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": ",".join(hourly),
        "daily": ",".join(daily),
        "current": ",".join(current),
        "forecast_days": forecast_days,
        "timezone": timezone,
    }
    r = requests.get(FORECAST_URL, params=params, timeout=25)
    r.raise_for_status()
    return r.json()


def weather_code_to_emoji(code: int) -> str:
    """간단한 날씨 아이콘 매핑 (필요시 더 촘촘히 확장 가능)"""
    if code in (0,):
        return "☀️ 맑음"
    if code in (1, 2):
        return "🌤 구름 조금"
    if code == 3:
        return "☁️ 흐림"
    if code in (45, 48):
        return "🌫 안개"
    if code in (51, 53, 55, 61, 63, 65):
        return "🌧 비"
    if code in (71, 73, 75, 77, 85, 86):
        return "❄️ 눈"
    if code in (80, 81, 82):
        return "🌦 소나기"
    if code in (95, 96, 99):
        return "⛈ 뇌우"
    return f"코드 {code}"


# ----------------------------
# 사이드바: 입력 구성
# ----------------------------
with st.sidebar:
    st.header("도시 선택")
    default_city = "세종"
    hint = "예: 서울, 세종, 부산, 대전, 제주 ..."
    city_kr = st.text_input("한글 도시명 입력", value=default_city, placeholder=hint)
    st.caption("맵에 없는 도시는 추가 요청 주세요!")

    st.divider()
    st.header("옵션")
    days = st.slider("예보 일수", min_value=3, max_value=14, value=7, step=1)
    show_hourly = st.checkbox("시간별(24시간) 보기", value=True)
    st.caption("네트워크/기관망인 경우, 프록시/인증서 설정이 필요할 수 있어요.")

# ----------------------------
# 본문 처리
# ----------------------------
if not city_kr:
    st.info("왼쪽에서 도시명을 입력하세요.")
    st.stop()

try:
    with st.spinner("지오코딩 중..."):
        loc = geocode_city(city_kr.strip())
    st.success(f"📍 {loc['name_kr']} ({loc['name_en']}) — lat={loc['lat']:.4f}, lon={loc['lon']:.4f}")
except Exception as e:
    st.error(f"지오코딩 실패: {e}")
    st.stop()

try:
    with st.spinner("날씨를 불러오는 중..."):
        data = fetch_forecast(loc["lat"], loc["lon"], forecast_days=days)
except requests.exceptions.SSLError:
    st.error("SSL 인증서 문제로 API에 연결할 수 없습니다. (기관망이라면 pip-system-certs 설치/프록시 설정을 확인하세요.)")
    st.stop()
except Exception as e:
    st.error(f"예보 호출 실패: {e}")
    st.stop()

# ----------------------------
# 현재 날씨 카드
# ----------------------------
cur = data.get("current", {})
cur_units = data.get("current_units", {})
col1, col2, col3, col4 = st.columns(4)
col1.metric("현재기온", f"{cur.get('temperature_2m', '—')}{cur_units.get('temperature_2m','°C')}")
col2.metric("체감기온", f"{cur.get('apparent_temperature', '—')}{cur_units.get('apparent_temperature','°C')}")
col3.metric("습도", f"{cur.get('relative_humidity_2m', '—')}{cur_units.get('relative_humidity_2m','%')}")
col4.metric("풍속", f"{cur.get('wind_speed_10m', '—')}{cur_units.get('wind_speed_10m','m/s')}")

wc_text = weather_code_to_emoji(int(cur.get("weather_code", -1))) if cur.get("weather_code") is not None else "—"
st.caption(f"현재 상태: {wc_text} · 시각: {cur.get('time', '—')}")

st.divider()

# ----------------------------
# 일별 예보 표 + 차트
# ----------------------------
daily = data.get("daily", {})
if daily:
    df_daily = pd.DataFrame({
        "date": pd.to_datetime(daily.get("time", [])),
        "tmax": daily.get("temperature_2m_max", []),
        "tmin": daily.get("temperature_2m_min", []),
        "precip_sum": daily.get("precipitation_sum", []),
        "sunrise": pd.to_datetime(daily.get("sunrise", [])),
        "sunset": pd.to_datetime(daily.get("sunset", [])),
    }).set_index("date")

    st.subheader("📅 일별 예보")
    st.dataframe(df_daily, use_container_width=True)

    c1, c2 = st.columns(2)
    with c1:
        st.write("최고/최저 기온(°C)")
        st.line_chart(df_daily[["tmax", "tmin"]])
    with c2:
        st.write("일강수량(mm)")
        st.bar_chart(df_daily[["precip_sum"]])

# ----------------------------
# 시간별(다음 24시간) 예보
# ----------------------------
if show_hourly:
    hourly = data.get("hourly", {})
    if hourly and hourly.get("time"):
        df_hourly = pd.DataFrame({
            "time": pd.to_datetime(hourly["time"]),
            "temp": hourly.get("temperature_2m", []),
            "humidity": hourly.get("relative_humidity_2m", []),
            "precip": hourly.get("precipitation", []),
            "wind": hourly.get("wind_speed_10m", []),
            "wcode": hourly.get("weather_code", []),
        }).set_index("time").iloc[:24]

        st.subheader("🕒 시간별(다음 24시간)")
        c3, c4 = st.columns(2)
        with c3:
            st.write("기온(°C)")
            st.line_chart(df_hourly[["temp"]])
        with c4:
            st.write("풍속(m/s)")
            st.line_chart(df_hourly[["wind"]])

        st.write("강수량(mm)")
        st.bar_chart(df_hourly[["precip"]])

# 푸터
st.caption("Data © Open-Meteo · Timezone: Asia/Seoul")
