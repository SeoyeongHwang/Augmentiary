import streamlit as st
import openai  # OpenAI API 사용
import anthropic
import firebase_admin
from firebase_admin import credentials, firestore
from streamlit_extras.let_it_rain import rain
from streamlit_extras.stylable_container import stylable_container
from utils.api_client import DiaryAnalyzer
from datetime import datetime
from zoneinfo import ZoneInfo

# 한국시간 설정
kst = ZoneInfo('Asia/Seoul')

# 페이지 설정
st.set_page_config(
    page_title="하루를 돌아보기",
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
def handle_login(user_id, password):
    # Firestore에서 사용자 문서 가져오기
    user_doc = db.collection("users").document(user_id).get()
    # 사용자 문서가 존재하는지 확인
    if user_doc.exists:
        user_data = user_doc.to_dict()
        # 비밀번호 검증
        if "password" in user_data and user_data["password"] == password:
            # 로그인 성공 처리
            st.session_state["user_id"] = user_data["id"]
            st.session_state["session_id"] = start_session_with_log(user_data["id"])
            st.session_state["show_welcome_message"] = True  # 로그인 성공 플래그 추가

            # 화면 갱신
            st.rerun()
        else:
            st.error("잘못된 비밀번호입니다.")
    else:
        st.error("존재하지 않는 아이디입니다.")

# 세션 시작 및 활동 기록 함수
def start_session_with_log(user_id):
    # 고유한 세션 ID 생성
    session_id = f"{user_id}_{datetime.now(kst).strftime('%Y%m%d%H%M%S')}"

    # Firestore 참조
    logs_ref = db.collection("users").document(user_id).collection("logs").document(session_id)
    api_responses_ref = db.collection("users").document(user_id).collection("api_responses").document(session_id)

    # 세션 logs 초기화
    logs_ref.set({
        "start_time": datetime.now(kst),
        "end_time": None,  # 초기값 null
        "activities": []   # 활동 배열 초기화
    })

    # 세션 api_responses 초기화
    api_responses_ref.set({
        "responses": []  # 빈 배열로 초기화
    })

    # 로그인 활동 기록 추가
    log_activity(user_id, session_id, "Logged in")

    print(f"► Session {session_id} started and handle_login activity recorded for user {user_id}.")
    return session_id

def upload_initial_diary(user_id: str, diary_entry: str):
    try:
        # 세션 ID 가져오기
        session_id = st.session_state.get("session_id")

        # 저장
        save_to_firebase(user_id, session_id, diary_entry, "initial_diaries", 1)

        # 활동 로그
        log_activity(user_id, session_id, "Wrote initial diary entry")
    except Exception as e:
        print(f"► Error uploading initial diary: {e}")

def save_diary(user_id: str, diary_entry: str):
    if diary_entry.strip():
        try:
            # 도큐먼트 카운터 기본값 설정
            if "save_counter" not in st.session_state:
                st.session_state["save_counter"] = 1
            else:
                st.session_state["save_counter"] += 1
            doc_counter = st.session_state["save_counter"]

            # 세션 ID 가져오기
            session_id = st.session_state.get("session_id")

            # 저장
            save_to_firebase(user_id, session_id, diary_entry, "saved_diaries", doc_counter)

            # 활동 로그
            log_activity(user_id, session_id, "Saved diary entry")
        except Exception as e:
            st.toast("일기를 저장하는 중 오류가 발생했어요. 잠시 후 다시 시도해 주세요.", icon=":material/error:")
            print(f"► Error saving diary: {e}")

def upload_working_diary(user_id: str, diary_entry: str):
    if diary_entry.strip():
        try:
            # 도큐먼트 카운터 기본값 설정
            if "working_counter" not in st.session_state:
                st.session_state["working_counter"] = 1
            else:
                st.session_state["working_counter"] += 1
            doc_counter = st.session_state["working_counter"]

            # 세션 ID 가져오기
            session_id = st.session_state.get("session_id")

            # 저장
            save_to_firebase(user_id, session_id, diary_entry, "working_diaries", doc_counter)

            # 활동 로그
            log_activity(user_id, session_id, "Modified diary entry")
        except Exception as e:
            print(f"► Error uploading working diary: {e}")

def save_to_firebase(user_id: str, session_id: str, entry: str, entry_type: str, doc_counter: int):
    try:
        # 현재 시간 기록
        timestamp = datetime.now(kst).isoformat()
        
        # Firestore 컬렉션 참조
        doc_ref = db.collection("users").document(user_id).collection(entry_type).document(f'{session_id}_{doc_counter}')
        # 데이터 저장
        doc_ref.set({
            'entry' : entry,
            'timestamp' : timestamp
        })
    except Exception as e:
        st.error(f"Firebase 저장 중 오류 발생: {e}")


# API 요청 및 응답 정보 저장
def save_api_response(user_id: str, session_id: str, diary_entry: str, result: str, life_orientation: str, tone: str, doc_counter: int): #value 제외
    # 현재 시간 기록
    timestamp = datetime.now(kst).isoformat()

    # Firestore 컬렉션 참조
    session_ref = db.collection("users").document(user_id).collection("api_responses").document(session_id)

    session_doc = session_ref.get()
    if session_doc.exists:
        responses = session_doc.to_dict().get("responses", [])

        # 데이터 저장
        responses.append({
            'life_orientation': life_orientation,  # 사용자가 선택한 삶의 태도
            #'value': value,                 # 선택된 가치
            'tone': tone,                   # 선택된 어조
            'input_entry': diary_entry,     # 입력으로 사용된 일기
            'result': result,               # AI 일기 생성 결과
            'timestamp': timestamp          # 저장 시간
        })
        session_ref.update({"responses": responses})
        print(f"► API 응답 저장 완료: {session_ref.id}")
    else:
        print(f"► API 요청 및 응답 정보 저장 중 오류 발생")

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
            "timestamp": datetime.now(kst)
        })
        session_ref.update({"activities": activities})
        print(f"► Activity '{activity}' logged for session {session_id}.")
    else:
        print(f"► Session {session_id} does not exist for user {user_id}.")

# textarea 콜백 함수
def handle_entry_interaction():
    """
    Textarea 상호작용 콜백 함수.
    - 첫 상호작용: 초기 일기 저장 및 데이터베이스 저장.
    - 이후 상호작용: 일기 업데이트 및 수정 로그 기록.
    """
    try:
        user_id = st.session_state.get("user_id")
        session_id = st.session_state.get("session_id")
        diary_entry = st.session_state.get("diary_entry", "").strip()  # Textarea 값 가져오기

        # Textarea 입력이 비어있는 경우 처리하지 않음
        if not diary_entry: return

        # 첫 상호작용 처리
        if "initial_entry" not in st.session_state:
            st.session_state["diary_entry"] = diary_entry
        # 이후 상호작용 처리
        else:
            # 일기 업데이트
            st.session_state["diary_entry"] = diary_entry
            log_activity(user_id, session_id, "Modified diary entry")
    except Exception as e:
        st.error(f"Textarea 상호작용 처리 중 오류 발생: {e}")

# API 요청 콜백 함수
def handle_api_request(spinner_container):
    # expander 닫기
    st.session_state.expander_state = False

    # 필수 데이터 확인
    diary_entry = st.session_state.get("diary_entry")
    life_orientation = st.session_state.get("life_orientation")
    #value = st.session_state.get("value")
    tone = st.session_state.get("tone")

    # 필수 데이터가 없는 경우 경고 메시지 표시
    if not all([diary_entry, life_orientation, tone]): #value 제외
        st.toast("아직 작성된 내용이 없어요.일기를 쓰고 원하는 옵션을 선택하시면 새로운 관점을 찾아드릴게요.", icon=':material/error:')
        st.session_state["is_loading"] = False
        return

    user_id = st.session_state.get("user_id")
    session_id = st.session_state.get("session_id")

    # 첫 요청인 경우 처음 일기 엔트리 저장
    if 'initial_entry' not in st.session_state:
        st.session_state['initial_entry'] = diary_entry
        upload_initial_diary(user_id, diary_entry)
    
    # 활동 로그 기록
    log_activity(user_id, session_id, "Requested AI response")

    # API 호출 및 결과 저장
    with spinner_container.container():
        with st.spinner("일기를 읽고 있어요. 잠시만 기다려 주세요..."):
            try:
                result = analyzer.augment_diary_v2(
                    diary_entry=diary_entry,
                    life_orientation=life_orientation,
                    #value=value,
                    tone=tone,
                    method="perspective"
                )
                # 결과를 세션 상태에 저장
                st.session_state["analysis_result"] = result
                st.session_state["result_life_orientation"] = life_orientation
                #st.session_state["result_value"] = value
                st.session_state["result_tone"] = tone
                st.session_state["show_update_entry_button"] = True
                st.session_state['show_rain'] = True

                # 도큐먼트 카운터 기본값 설정
                if "response_counter" not in st.session_state:
                    st.session_state["response_counter"] = 1
                else:
                    st.session_state["response_counter"] += 1
                doc_counter = st.session_state["response_counter"]

                # Firestore에 API 결과와 선택 옵션 저장
                save_api_response(user_id, session_id, diary_entry, result, life_orientation, tone, doc_counter) #value 제외

            except Exception as e:
                st.error(f"API 요청 중 오류 발생: {e}")

# 탭 확장 여부 함수
def toggle_expander_state():
    st.session_state.expander_state = False  # 상태 토글

# 가져오기 버튼 핸들
def handle_entry_update():
    """
    "내 일기에 담기" 버튼 클릭 시 실행되는 콜백 함수.
    - 분석 결과를 일기 입력 필드에 저장.
    - 활동 로그 기록.
    """
    try:
        # 분석 결과를 Textarea 상태에 반영
        st.session_state.diary_entry = st.session_state.get('analysis_result')

        # 활동 로그 기록
        log_activity(
            st.session_state['user_id'],
            st.session_state["session_id"],
            "Applied AI-augmented diary."
        )
        st.toast("내용을 가져왔어요. 이제 내용을 자유롭게 수정하실 수 있어요.", icon=":material/check:")
        print('► 적용: \n', st.session_state.diary_entry)
    except Exception as e:
        st.error(f"일기 업데이트 중 오류 발생: {e}")

# 저장하기 버튼 핸들
def handle_diary_save():
    try:
        user_id = st.session_state.get("user_id")
        # 엔트리 저장
        if diary_entry.strip():
            save_diary(user_id, diary_entry)
            st.toast("일기 한 편을 완성했어요!", icon=":material/check:")
            st.session_state["save_success"] = True
        else:
            st.toast("아직 작성된 내용이 없어요. 먼저 일기 한 편을 써보세요.", icon=":material/error:")
    except Exception as e:
        st.error(f"일기 저장 중 오류 발생: {e}")

# 원래대로 버튼 핸들
def handle_load_original():
    if "initial_entry" not in st.session_state:
        st.toast("아직 작성된 내용이 없어요. 먼저 일기 한 편을 써보세요.", icon=":material/error:")
    else:
        user_id = st.session_state.get('user_id')
        session_id = st.session_state.get('session_id')

        # 업데이트
        st.session_state['diary_entry'] = st.session_state['initial_entry']

        # 활동 로그
        log_activity(user_id, session_id, "Went back to the original diary")

        # 알림
        st.toast("처음 작성한 일기로 복원됐어요.", icon=":material/check:")

# OpenAI API Key 설정
def initialize_openai_api():
    api_key_gpt = st.secrets["general"]["OPENAI_API_KEY"]
    api_key_claude = st.secrets["general"]["ANTHROPIC_API_KEY"]
    return api_key_gpt, api_key_claude

## -------------------------------------------------------------------------------------------------
## Not logged in -----------------------------------------------------------------------------------
## -------------------------------------------------------------------------------------------------
# Firebase 기반 로그인 UI. 로그인 성공 시 세션에 user_id와 session_id 저장
if "session_id" not in st.session_state:
    c1, c2, c3 = st.columns([0.25, 0.5, 0.25], vertical_alignment="top")
    with c2:
        st.title("시작하기")
        user_id = st.text_input("아이디", placeholder="아이디를 입력해주세요.")
        password = st.text_input("비밀번호", type="password", placeholder="비밀번호를 입력해주세요.", kwargs={"autocomplete": "off"})

        if st.button("Login", use_container_width=True):
            handle_login(user_id, password)
## -------------------------------------------------------------------------------------------------
## Logged in --------------------------------------------------------------------------------------
## -------------------------------------------------------------------------------------------------
else:  
    # 로그인 성공 안내 메시지: 플래그가 활성화된 경우에만 표시
    if st.session_state.get("show_welcome_message", False):
        st.toast(f"{st.session_state['user_id']}님, 환영해요!", icon=":material/waving_hand:")
        st.session_state["show_welcome_message"] = False  # 메시지 표시 후 플래그 비활성화
        print("► 세션: "+st.session_state["session_id"])

    # API 클라이언트 초기화
    @st.cache_resource
    def get_analyzer():
        api_key_gpt, api_key_claude = initialize_openai_api()  # Retrieve the API keys
        return DiaryAnalyzer(api_key_gpt, api_key_claude)  # 설정된 API 키 사용

    analyzer = get_analyzer()
    
    if st.session_state.get("save_success", False):
        rain(
            emoji="👍",
            font_size=36,
            falling_speed=10,
            animation_length="0.5",
        )
        st.session_state["save_success"] = False
    
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
    current_date = datetime.now(kst)
    current_day = current_date.strftime('%A')  # 영어 요일 가져오기
    translated_day = day_translation.get(current_day, current_day)  # 한국어로 변환

    # 타이틀
    st.markdown(
        f"<h2 style='text-align: left; padding: 0; margin-bottom: 40px;'>{current_date.strftime('%m월 %d일')} {translated_day}</h2>", 
        unsafe_allow_html=True
    )

    life_orientation_map = {
        "future-oriented":"미래지향적", 
        "realisty-based":"현실적", 
        "optimistic":"낙관적", 
        "growth-oriented":"성장주의적", 
        "accepting":"수용적"
    }
    life_orientation_map_v2 = {
        "future-oriented":"Future-oriented", 
        "reality-based":"Realistic", 
        "optimistic":"Optimistic", 
        "growth-oriented":"Growth-oriented", 
        "accepting":"Accepting"
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
    tone_map_v2 = {
        "my_tone": "💁 As I wrote it",
        "warm": "😁 Warm and friendly", 
        "calm": "🍵 Calm and peaceful", 
        "funny": "🤡 Playful and cheerful",
        "emotional": "🌌 Gentle and emotional" 
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

    col1, col2 = st.columns([0.5, 0.5], vertical_alignment="top")

    with col1:
        # 일기 입력 섹션
        diary_entry = st.text_area(
            "diary_entry", 
            placeholder="Feel free to write about the events, thoughts, and feelings you experienced.", 
            height=462, 
            label_visibility="collapsed",
            disabled=False,
            on_change=handle_entry_interaction,
            key="diary_entry",  # Textarea 값 세션 상태와 연결
        )

        btn1, btn2 = st.columns(2)
        with btn1:
            # 원래 처음에 입력한 일기로 돌아가기
            st.button("Back to Original", icon=":material/refresh:", type='secondary', use_container_width=True, on_click=handle_load_original)
        with btn2:
            # 일기 저장하기
            st.button("Save Entry", icon=":material/save:", type="secondary", use_container_width=True, on_click=handle_diary_save)

    with col2:
        selector = st.expander("See this day a little differently", icon="🔮", expanded=st.session_state.get("expander_state", True))  # 세션 상태 사용
        # 옵션 선택 섹션 - life_orientation
        selector.text("How would you like to view this day?")
        life_orientation = selector.pills(
            "Life-orientation", 
            options=life_orientation_map_v2.keys(), 
            format_func=lambda option: life_orientation_map_v2[option], 
            label_visibility="collapsed"
        ) or None
        if life_orientation:
            st.session_state["life_orientation"] = life_orientation
        # 옵션 선택 섹션 - value
        #selector.text("나에게 소중한 가치는")
        #value = selector.pills(
        #    "가치 선택", 
        #    options=value_map.keys(), 
        #    format_func=lambda option: value_map[option], 
        #    label_visibility="collapsed"
        #) or None
        #if value:
        #    st.session_state["value"] = value
        # 옵션 선택 세션 - tone
        selector.text("Which mood would you like to use to write this?")
        tone = selector.pills(
            "Tone", 
            options=tone_map_v2.keys(), 
            format_func=lambda option: tone_map_v2[option], 
            label_visibility="collapsed"
        ) or None
        if tone:
            st.session_state["tone"] = tone

        if 'analysis_result' not in st.session_state:
            st.session_state.analysis_result = None
        
        # 스피너 및 결과 컨테이너
        spinner_container = st.empty()
        result_container = st.empty()

        with selector:
            if st.session_state.get('diary_entry', False):
                st.session_state["button_disabled"] = False

            # 결과 요청 버튼
            st.button(
                "🪄 Get a New Perspective", 
                type='secondary', 
                use_container_width=True, 
                disabled=st.session_state.get("button_disabled", True),
                on_click=handle_api_request,
                args=(spinner_container,), # spinner_container를 인자로 전달
            )

        # 결과를 입력 필드에 적용하는 버튼 추가
        if st.session_state.get('show_update_entry_button', False):  # 버튼 표시 플래그 확인
            st.button("Replace My Diary", icon=':material/north_west:', type='secondary', on_click=handle_entry_update)

        if st.session_state.get('show_rain'):
            rain(emoji="🍀", font_size=36, falling_speed=10, animation_length="1",)
            st.session_state.show_rain = False

        # 결과가 있다면 항상 표시
        if st.session_state.analysis_result:
            with result_container.container(height=400, border=None):
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
                    description.markdown(f":violet[Here's how you might see it from a **{life_orientation_map_v2[st.session_state.result_life_orientation]}** perspective.]")
                # 선택된 태그
                with st.container():
                    tags = st.container()
                    tags.markdown(f":violet[_#{life_orientation_map_v2[st.session_state.result_life_orientation]}  #{tone_map_v2[st.session_state.result_tone]}_]") ##{value_map[st.session_state.result_value]} 제외
                # 결과
                container = st.container()
                container.write(st.session_state.analysis_result)

    