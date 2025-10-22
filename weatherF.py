import requests

# ----------------------------
# ① 한글 → 영문 도시명 매핑
# ----------------------------
CITY_MAP = {
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
# ② 지오코딩 (도시 이름 → 위도/경도)
# ----------------------------
def geocode_city(korean_name):
    eng_name = CITY_MAP.get(korean_name)
    if not eng_name:
        raise ValueError(f"❌ '{korean_name}'은(는) 지원하지 않는 도시입니다.")
    
    params = {
        "name": eng_name,
        "count": 1,
        "language": "ko",
        "country_code": "KR",
        "format": "json"
    }
    r = requests.get(GEO_URL, params=params, timeout=20)
    r.raise_for_status()
    data = r.json()
    if not data.get("results"):
        raise ValueError(f"❌ 검색 결과가 없습니다: {korean_name} ({eng_name})")
    loc = data["results"][0]
    return {
        "name_kr": korean_name,
        "name_en": eng_name,
        "lat": loc["latitude"],
        "lon": loc["longitude"]
    }

# ----------------------------
# ③ 날씨 데이터 조회
# ----------------------------
def fetch_forecast(lat, lon, timezone="Asia/Seoul"):
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,sunrise,sunset",
        "forecast_days": 3,
        "timezone": timezone
    }
    r = requests.get(FORECAST_URL, params=params, timeout=20)
    r.raise_for_status()
    return r.json()

# ----------------------------
# ④ 결과 출력
# ----------------------------
def show_weather(city_kr):
    loc = geocode_city(city_kr)
    print(f"\n📍 {loc['name_kr']} ({loc['name_en']})")
    print(f"위도: {loc['lat']}, 경도: {loc['lon']}")
    
    data = fetch_forecast(loc["lat"], loc["lon"])
    cur = data.get("current", {})
    print("\n🌤 현재 날씨")
    print(f"  기온: {cur.get('temperature_2m')}°C")
    print(f"  체감: {cur.get('apparent_temperature')}°C")
    print(f"  습도: {cur.get('relative_humidity_2m')}%")
    print(f"  강수량: {cur.get('precipitation')}mm")
    print(f"  풍속: {cur.get('wind_speed_10m')}m/s")
    
    daily = data.get("daily", {})
    print("\n📅 3일간 예보 (최고/최저기온)")
    for d, tmax, tmin in zip(daily["time"], daily["temperature_2m_max"], daily["temperature_2m_min"]):
        print(f"  {d}: 최고 {tmax}°C / 최저 {tmin}°C")

# ----------------------------
# ⑤ 실행부
# ----------------------------
if __name__ == "__main__":
    city_input = input("도시 이름을 입력하세요 (예: 서울, 세종, 부산): ").strip()
    try:
        show_weather(city_input)
    except Exception as e:
        print(e)
