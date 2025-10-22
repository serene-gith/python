# app.py
from __future__ import annotations

import time
import requests
import pandas as pd
import streamlit as st
from dataclasses import dataclass
from typing import Dict, Iterable

# ========== 공통 UI 설정 ==========
st.set_page_config(page_title="환율 + 챗봇 (Streamlit)", page_icon="💱", layout="centered")

# ========== 환율 섹션 ==========
API_BASE = "https://open.er-api.com/v6/latest"  # 키 불필요
DEFAULT_BASE = "USD"
DEFAULT_TARGETS = ["KRW", "JPY", "EUR", "CNY", "GBP"]
CACHE_TTL_SEC = 60  # Streamlit 캐시 TTL(초)

@dataclass
class FXSnapshot:
    base: str
    timestamp_utc: int
    rates: Dict[str, float]

@st.cache_data(ttl=CACHE_TTL_SEC, show_spinner=False)
def fetch_latest_rates(base: str) -> FXSnapshot:
    base = base.upper().strip()
    url = f"{API_BASE}/{base}"
    r = requests.get(url, timeout=8)
    r.raise_for_status()
    data = r.json()
    if data.get("result") != "success":
        raise RuntimeError(data.get("error-type", "API error"))
    return FXSnapshot(
        base=data["base_code"],
        timestamp_utc=data["time_last_update_unix"],
        rates=data["rates"],
    )

def filter_rates(rates: Dict[str, float], targets: Iterable[str]) -> Dict[str, float]:
    targets = [t.upper().strip() for t in targets if t.strip()]
    return {k: v for k, v in rates.items() if k in targets}

def convert_amount(amount: float, from_code: str, to_code: str, snap: FXSnapshot) -> float:
    from_code = from_code.upper().strip()
    to_code = to_code.upper().strip()
    if from_code == snap.base and to_code in snap.rates:
        return amount * snap.rates[to_code]
    if to_code == snap.base and from_code in snap.rates:
        return amount / snap.rates[from_code]
    if from_code in snap.rates and to_code in snap.rates:
        return (amount / snap.rates[from_code]) * snap.rates[to_code]
    raise ValueError(f"지원되지 않는 통화 조합: {from_code} -> {to_code}")

def rates_tab():
    st.title("💱 환율 대시보드 (키 불필요)")
    with st.sidebar:
        st.subheader("환율 옵션")
        base = st.text_input("기준 통화 (BASE)", value=DEFAULT_BASE, max_chars=3).upper()
        targets_raw = st.text_input("표시 통화(쉼표로 구분)", value=",".join(DEFAULT_TARGETS))
        amount = st.number_input("금액 (기준 통화 금액)", min_value=0.0, value=100.0, step=10.0)
        run = st.button("환율 조회")

    if not run:
        run = True  # 첫 렌더에서도 조회

    if run:
        try:
            snap = fetch_latest_rates(base)
            targets = [t.strip().upper() for t in targets_raw.split(",")]
            sel = filter_rates(snap.rates, targets)

            if not sel:
                st.warning("표시할 통화가 없습니다. targets를 확인하세요.")
                return

            df = pd.DataFrame(
                {
                    "currency": list(sorted(sel.keys())),
                    "rate": [sel[k] for k in sorted(sel.keys())],
                }
            )
            df[f"{amount:.2f} {snap.base} →"] = (amount * df["rate"]).map(lambda x: f"{x:,.2f}")

            st.markdown(f"**기준 통화:** `{snap.base}`  |  **업데이트(UTC):** {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(snap.timestamp_utc))}")
            st.dataframe(df, use_container_width=True)

            # CSV 다운로드
            csv_bytes = df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "CSV 다운로드",
                data=csv_bytes,
                file_name=f"rates_{snap.base}.csv",
                mime="text/csv",
            )

            # 역변환 예시
            try:
                ex = convert_amount(amount=10_000, from_code="KRW", to_code=snap.base, snap=snap)
                st.caption(f"예시) 10,000 KRW → {snap.base}: **{ex:,.2f} {snap.base}**")
            except Exception:
                pass

        except Exception as e:
            st.error(f"환율 조회 중 오류: {e}")

# ========== 챗봇 섹션 ==========
def get_openai_client(api_key: str, base_url: str | None):
    """
    OpenAI 공식 SDK v1.x 사용.
    - base_url이 있으면 LM Studio / LocalAI 등 OpenAI-호환 서버도 사용 가능.
    """
    from openai import OpenAI
    if base_url and base_url.strip():
        return OpenAI(api_key=api_key, base_url=base_url.strip())
    return OpenAI(api_key=api_key)

def chatbot_tab():
    st.title("🤖 챗봇 (OpenAI 또는 로컬 OpenAI-호환 서버)")

    with st.sidebar:
        st.subheader("모델/키 설정")
        provider = st.selectbox("백엔드 선택", ["OpenAI (클라우드)", "로컬/사내 OpenAI-호환 서버"], index=0)
        if provider.startswith("OpenAI"):
            api_key = st.text_input("OpenAI API Key", type="password", placeholder="sk-...", key="openai_key")
            base_url = ""  # 기본(공식) 엔드포인트
        else:
            api_key = st.text_input("로컬 서버용 API Key(더미도 가능)", type="password", value="lm-studio", key="local_key")
            base_url = st.text_input("Base URL", value="http://localhost:1234/v1", help="예) LM Studio: http://localhost:1234/v1, LocalAI: http://localhost:8080/v1")
        model = st.text_input("모델 이름", value="gpt-4o-mini", help="LM Studio/LocalAI일 경우 서버에 로드된 모델 id를 입력")
        temperature = st.slider("창의성 (temperature)", 0.0, 1.5, 0.7, 0.1)
        sys_prompt = st.text_area("시스템 프롬프트(선택)", value="당신은 유능한 한국어 어시스턴트입니다.", height=80)

    # 세션 상태 초기화
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []
    if "chat_model" not in st.session_state:
        st.session_state.chat_model = model

    # 모델이 바뀌면 대화 초기화 (상태 꼬임 방지)
    if model != st.session_state.chat_model:
        st.session_state.chat_model = model
        st.session_state.chat_messages = []
        st.toast("모델 변경으로 대화를 새로 시작합니다.", icon="♻️")

    # 과거 메시지 렌더
    for m in st.session_state.chat_messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    user_input = st.chat_input("메시지를 입력하세요…")
    if user_input:
        st.session_state.chat_messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        # 호출
        try:
            client = get_openai_client(api_key=api_key, base_url=base_url if provider.startswith("로컬") else None)

            # messages 구성
            messages = []
            if sys_prompt.strip():
                messages.append({"role": "system", "content": sys_prompt.strip()})
            messages.extend(st.session_state.chat_messages)

            # 응답 생성 (비스트리밍)
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
            )
            content = resp.choices[0].message.content

            with st.chat_message("assistant"):
                st.markdown(content)

            st.session_state.chat_messages.append({"role": "assistant", "content": content})

        except Exception as e:
            st.error(f"요청 실패: {e}\n\n- API Key/모델/URL이 올바른지 확인하세요.\n- 로컬 서버라면 실제로 모델이 로드되어 있는지 확인하세요.")

# ========== 탭 구성 ==========
tab1, tab2 = st.tabs(["💱 환율", "🤖 챗봇"])
with tab1:
    rates_tab()
with tab2:
    chatbot_tab()
