import streamlit as st
import openai  # OpenAI API 사용
import firebase_admin
from firebase_admin import credentials, auth, firestore
from streamlit_extras.let_it_rain import rain
from streamlit_extras.stylable_container import stylable_container
from utils.api_client import DiaryAnalyzer
from datetime import datetime
import pyperclip  # pyperclip 라이브러리 추가
import pytz
from st_copy_to_clipboard import st_copy_to_clipboard
from werkzeug.security import check_password_hash  # 해싱 검증 함수

# 페이지 설정
st.set_page_config(
    page_title="오늘 하루 돌아보기",
    layout="wide"  # 넓은 레이아웃 설정
)

# 폰트 적용
def load_css(filename):
    with open(filename) as f:
        st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)
load_css('style.css')

# Firebase 초기화
if not firebase_admin._apps:
    firebase_config = {
        "type": st.secrets["firebase"]["type"],
        "project_id": st.secrets["firebase"]["project_id"],
        "private_key_id": st.secrets["firebase"]["private_key_id"],
        "private_key": st.secrets["firebase"]["private_key"],
        "client_email": st.secrets["firebase"]["client_email"],
        "client_id": st.secrets["firebase"]["client_id"],
        "auth_uri": st.secrets["firebase"]["auth_uri"],
        "token_uri": st.secrets["firebase"]["token_uri"],
    }
    cred = credentials.Certificate(firebase_config)
    firebase_admin.initialize_app(cred)

db = firestore.client()  # Firestore 클라이언트

# 로그인 처리 (유저 정보 로드)
def login(user_id, password):
    # Firestore에서 사용자 문서 가져오기
    user_doc = db.collection("users").document(user_id).get()
    # 사용자 문서가 존재하는지 확인
    if user_doc.exists:
        user_data = user_doc.to_dict()
        print(user_data)
        # 비밀번호 검증
        if "password" in user_data and user_data["password"] == password:
            # 로그인 성공 처리
            st.session_state["user_id"] = user_data["id"]
            session_id = start_session_with_log(user_data["id"])

            # 화면 갱신
            st.rerun()
        else:
            st.error("잘못된 비밀번호입니다.")
    else:
        st.error("존재하지 않는 아이디입니다.")

# 세션 시작 및 활동 기록 함수
def start_session_with_log(user_id):
    # 고유한 세션 ID 생성
    session_id = f"{user_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"

    # Firestore 참조
    logs_ref = db.collection("users").document(user_id).collection("logs").document(session_id)

    # 세션 데이터 초기화
    logs_ref.set({
        "start_time": datetime.now(),
        "end_time": None,  # 초기값 null
        "activities": []   # 활동 배열 초기화
    })

    # 로그인 활동 기록 추가
    log_activity(user_id, session_id, "Logged in")

    print(f"Session {session_id} started and login activity recorded for user {user_id}.")
    return session_id

# Firestore에 데이터 저장
def save_diary(user_id, diary_entry):
    doc_ref = db.collection("diaries").document(user_id)
    data = {
        "entry": diary_entry,
        "timestamp": datetime.datetime.now()
    }
    
    # Firestore에 데이터 추가
    diary_ref = diaries_ref.add(data)  # 문서 ID 자동 생성
    diary_id = diary_ref[1].id
    print(f"Diary saved with ID: {diary_id}")

    # 활동 기록 추가
    session_id = get_active_session(user_id)
    if session_id:
        log_activity(user_id, session_id, f"Saved diary entry with ID: {diary_id}")

    st.success("Diary saved successfully!")

# 활동 기록 함수
def log_activity(user_id, session_id, activity):
    # Firestore에서 세션 문서 참조
    session_ref = db.collection("users").document(user_id).collection("logs").document(session_id)

    # 세션 데이터 가져오기
    session_doc = session_ref.get()
    if session_doc.exists:
        activities = session_doc.to_dict().get("activities", [])
        
        # 활동 추가
        activities.append({
            "activity": activity,
            "timestamp": datetime.now()
        })
        session_ref.update({"activities": activities})
        print(f"Activity '{activity}' logged for session {session_id}.")
    else:
        print(f"Session {session_id} does not exist for user {user_id}.")

# OpenAI API Key 설정
def initialize_openai_api():
    openai.api_key = st.secrets["general"]["OPENAI_API_KEY"]
initialize_openai_api()

## -------------------------------------------------------------------------------------------------
## Not logged in -----------------------------------------------------------------------------------
## -------------------------------------------------------------------------------------------------
# Firebase 기반 로그인 UI
if "user_id" not in st.session_state:
    st.title("일기 작성하러 가기")
    user_id = st.text_input("아이디", placeholder="아이디를 입력해주세요.")
    password = st.text_input("비밀번호", type="password", placeholder="비밀번호를 입력해주세요.", kwargs={"autocomplete": "off"})
    if st.button("Login", use_container_width=True):
        login(user_id, password)
## -------------------------------------------------------------------------------------------------
## Logged in --------------------------------------------------------------------------------------
## -------------------------------------------------------------------------------------------------
else:
    # 로그인 성공 안내 메시지
    st.toast(f"{st.session_state['user_id']}님, 환영합니다!", icon=":material/check:")

    # API 클라이언트 초기화
    @st.cache_resource
    def get_analyzer():
        return DiaryAnalyzer(openai.api_key)  # 설정된 API 키 사용

    analyzer = get_analyzer()

    # 초기 화면에서는 손 이모티콘 rain만 표시
    if 'analysis_result' not in st.session_state:
        rain(
            emoji="👋🏻",
            font_size=36,
            falling_speed=10,
            animation_length="0.5",
        )
    
    # 요일 변환 딕셔너리
    day_translation = {
        "Monday": "월요일",
        "Tuesday": "화요일",
        "Wednesday": "수요일",
        "Thursday": "목요일",
        "Friday": "금요일",
        "Saturday": "토요일",
        "Sunday": "일요일"
    }

    # 현재 날짜와 요일 가져오기
    # 한국시간 설정
    kst = pytz.timezone('Asia/Seoul')
    current_date = datetime.now(kst)
    current_day = current_date.strftime('%A')  # 영어 요일 가져오기
    translated_day = day_translation.get(current_day, current_day)  # 한국어로 변환

    # 타이틀
    st.markdown(
        f"<h2 style='text-align: center; padding: 0;'>{current_date.strftime('%m월 %d일')} {translated_day},</h2><h2 style='text-align: center; padding: 0; margin-bottom: 40px'>오늘</h2>",
        unsafe_allow_html=True
    )

    life_orientation_map = {
        "future-oriented":"미래지향적", 
        "realistic":"현실적", 
        "optimistic":"낙관적", 
        "growth-oriented":"성장주의적", 
        "accepting":"수용적"
    }
    value_map = {
        "balance":"균형", 
        "achievement":"성취", 
        "relationship":"관계", 
        "experience":"경험",
        "emotion":"감정"
    }
    tone_map = {
        "warm": "🤗 따뜻한",
        "friendly": "😁 친근한", 
        "calm": "🍵 차분한", 
        "funny": "🤡 장난스러운", 
        "emotional": "🌌 감성적인"
    }
    

    # "with" notation
    #with st.sidebar:
    #    add_radio = st.radio(
    #        "Choose a shipping method",
    #        ("Standard (5-15 days)", "Express (2-5 days)")
    #    )

    # 초기 상태 설정
    if 'expander_state' not in st.session_state:
        st.session_state.expander_state = True  # 기본적으로 열려 있음
    def toggle_expander_state():
        st.session_state.expander_state = False  # 상태 토글
        st.session_state.rerun_needed = True  # 새로 고침 필요 플래그 설정

    col1, col2 = st.columns([0.5, 0.5], vertical_alignment="top")

    with col1:
        # 일기 입력 섹션
        diary_entry = st.text_area(
            "diary_entry", 
            placeholder="오늘 있었던 일을 자유롭게 적어보세요.", 
            height=362, 
            label_visibility="collapsed",
            value=st.session_state.get('diary_entry_value', ''),  # session_state에서 값 가져오기
            disabled=False,
        )
        # diary_entry 수정 후 항상 diary_entry_value에 업데이트
        st.session_state.diary_entry_value = diary_entry  # 추가된 코드

        if st.button("복사하기", icon=":material/content_copy:", type='secondary'):
            # pyperclip.copy(st.session_state.diary_entry_value)  # 클립보드에 복사
            st.toast("현재 복사 기능은 지원되지 않습니다.\n필요한 경우 직접 복사 해주세요.", icon=":material/error:")  # 사용자에게 알림
            print('►복사: \n', st.session_state.diary_entry_value)

    with col2:
        selector = st.expander("하루에 관점 더하기", icon="🔮", expanded=st.session_state.expander_state)  # 세션 상태 사용
        # 옵션 선택 섹션 - life_orientation
        selector.text("오늘을 바라보고픈 태도는")
        life_orientation = selector.pills(
            "삶의 태도", 
            options=life_orientation_map.keys(), 
            format_func=lambda option: life_orientation_map[option], 
            label_visibility="collapsed"
        )
        # 옵션 선택 섹션 - value
        selector.text("나에게 소중한 가치는")
        value = selector.pills(
            "가치 선택", 
            options=value_map.keys(), 
            format_func=lambda option: value_map[option], 
            label_visibility="collapsed"
        )
        # 옵션 선택 세션 - tone
        selector.text("나에게 편한 분위기는")
        tone = selector.pills(
            "언어 선택", 
            options=tone_map.keys(), 
            format_func=lambda option: tone_map[option], 
            label_visibility="collapsed")

        if 'analysis_result' not in st.session_state:
            st.session_state.analysis_result = None
        
        # 결과를 표시할 컨테이너
        result_container = st.empty()

        with selector:
            button_disabled = st.session_state.get('button_disabled', False)
            if selector.button("🪄 다시 바라보기", type='secondary', use_container_width=True, disabled=button_disabled, on_click=toggle_expander_state):
                if not life_orientation or not value or not tone or not diary_entry.strip():
                    st.warning("일기를 입력하고 모든 옵션 선택을 완료하면 새로운 관점을 찾아드릴게요.")
                else:
                    try:
                        st.session_state.rerun_needed = True  # 새로 고침 필요 플래그 설정
                        st.toast("일기에 새로운 관점을 추가하고 있어요!", icon=":material/flare:")  # 사용자에게 알림
                        with result_container:
                            with st.spinner("잠시만 기다려주세요..."):
                                result = analyzer.augment_diary(
                                    diary_entry=diary_entry,
                                    life_orientation=life_orientation,
                                    value=value,
                                    tone=tone,
                                    method="langchain"
                                )

                                # 결과를 session_state에 저장
                                st.session_state.analysis_result = result
                                st.session_state.life_orientation = life_orientation  # 마지막 선택한 orientation 저장
                                st.session_state.value = value
                                st.session_state.tone = tone
                                st.session_state.show_result_rain = True  # rain 효과를 표시하기 위해 True로 설정
                                
                                # "내 일기에 담기" 버튼을 API 호출 후에만 표시
                                st.session_state.show_update_entry_button = True  # 버튼 표시 설정

                                # 페이지 새로 고침 필요 여부 확인
                                if st.session_state.get('rerun_needed', False):
                                    st.session_state.rerun_needed = False  # 플래그 초기화
                                    st.rerun()  # 페이지 새로 고침

                    except Exception as e:
                        st.error(f"오류 발생: {e}")

        # 결과를 입력 필드에 적용하는 버튼 추가
        if st.session_state.get('show_update_entry_button', False):  # 버튼 표시 플래그 확인
            update_entry = st.button("✍️ 내 일기에 담기", type='secondary')
            if update_entry:
                st.session_state.diary_entry_value = st.session_state.analysis_result  # LLM 결과를 session_state에 저장
                if 'entry_update_notice' not in st.session_state:
                    st.session_state.entry_update_notice = True  # 기본적으로 열려 있음
                print('►적용: \n', st.session_state.entry_update_notice)
                st.rerun()  # 페이지를 새로 고침하여 텍스트 영역 업데이트

    if st.session_state.get('entry_update_notice', False):
        st.session_state.entry_update_notice = False
        st.toast('일기를 성공적으로 가져왔어요! 가져온 내용을 수정할 수 있어요.', icon=":material/check:")

    # rain 효과 표시 (session_state에 저장된 상태에 따라)
    if st.session_state.get('show_result_rain', False):
        st.session_state.show_result_rain = False
        rain(
            emoji="🍀",
            font_size=36,
            falling_speed=10,
            animation_length="1",
        )

    # 결과가 있다면 항상 표시
    if st.session_state.analysis_result:
        with result_container.container(height=300, border=None):
            # 안내 메시지
            with stylable_container(
                key="description",
                css_styles="""
                {
                    border-radius: 4px;
                    padding: 10px 10px 10px 12px;
                    text-align: left;
                    white-space: normal;
                    word-wrap: keep-all;
                    background-color: rgba(155, 89, 182, 0.2);
                    line-height: 1.0;
                } 
                """
            ):
                description = st.container()
                description.markdown(f":violet[**{life_orientation_map[st.session_state.life_orientation]}** 시선을 담아 오늘을 이렇게 볼 수도 있어요.]")
            # 선택된 태그
            with st.container():
                tags = st.container()
                tags.markdown(f":violet[_#{life_orientation_map[st.session_state.life_orientation]}  #{value_map[st.session_state.value]}  #{tone_map[st.session_state.tone]}_]")
            # 결과
            container = st.container()
            container.write(st.session_state.analysis_result)

    