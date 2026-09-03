import streamlit as st
from common import ApiError, api, conversation_label, auth_headers,SERVICE_NAME, SessionExpired

"""18일차 완성본 — 사용자 상태와 개인화 UX.

오늘의 주제는 로그인 기능이 아니다. 백엔드의 로그인은 13일차에 이미 만들었다.
오늘 배우는 것은 **사용자 상태가 바뀔 때 화면이 어떻게 반응해야 하는가** 다.

    상태             조건                     화면
    -------------   ----------------------   --------------------------------
    비로그인         토큰 없음                 로그인 폼. 서비스가 뭔지도 알려줌
    로그인 + 빈 목록  연습 기록 0건             첫 면접을 시작하라는 안내
    로그인 + 선택 안함 목록은 있고 고르지 않음    무엇을 고르면 되는지
    로그인 + 내용 없음 대화는 있고 메시지 0건     예시 질문
    기본             주고받은 내용 있음         대화
    세션 만료         토큰이 60분을 넘김         왜 풀렸는지 + 다시 로그인

마지막 줄이 오늘 새로 생기는 상태다. 그리고 가장 많이 빠뜨리는 것이다.
"""

st.set_page_config(page_title=SERVICE_NAME)


#세션에 사용자id, 대화id를 저장한다.
# st.session_state.setdefault("user_id", "")
st.session_state.setdefault("access_token", None) #RLS 적용한 / me 라우터용
st.session_state.setdefault("user_email", None)

st.session_state.setdefault("conversation_id", None)

# 버튼으로 보낼 질문을 잠시 담아두는 곳. 버튼 안에서 바로 보내면
# 화면이 다시 그려지는 도중이라 결과가 화면에 안 나타난다.
st.session_state.setdefault("pending_question", None)

# 세션이 풀린 이유를 다음 실행에서 보여주려고 남겨둔다.
# 토큰만 지우고 끝내면 사용자는 자기가 왜 로그아웃됐는지 모른다.
st.session_state.setdefault("expired_notice", None)

EXAMPLE_QUESTIONS = [
    "면접을 시작해 주세요.",
    "1분 자기소개를 해보겠습니다.",
    "제 이력서에서 가장 많이 받을 질문이 뭘까요?",
]


@st.cache_data(ttl=300)
def load_options() -> dict:
    """선택지는 백엔드에서 받아온다.

    화면에 목록을 직접 적어두면 백엔드의 표와 두 곳에서 관리하게 된다.
    한쪽에 톤을 추가하고 다른 쪽을 잊으면, 버튼은 있는데 아무 효과가 없다.
    """
    return api("GET", "/chat/options")


def render_sidebar(options: dict, conversations: list) -> None:

    with st.sidebar :
        st.subheader("면접 연습용 대화 기록")
        #로그인한 사용자 이메일
        st.caption(st.session_state.user_email) 

        if st.button("로그아웃", use_container_width=True):
            sign_out()

        # st.text_input( #사용자 아이디 받는부분
        #     "사용자 ID(Profiles 테이블의 ID)", key="user_id"
        # )
        # if not st.session_state.user_id : #사용자 정보가 없을 때
        #     st.caption("user_id 를 입력하면 연습 기록이 나타납니다.")
        #     # 더이상 진행하지 않는다
        #     return


        st.divider()
        st.subheader("연습 기록")


        # try:
        #     conversations = api( #대화 목록 가져오는 곳
        #         "GET", "/conversations", params={"user_id": st.session_state.user_id}
        #     )
        # except ApiError as error: #대화가 없을 떄
        #     st.error(str(error))
        #     return

        #대화가 있을 떄 -> 보기좋게 한줄로 만들어주기
        if conversations: 
            labels = {c["id"]: conversation_label(c) for c in conversations} #리스트 컴프리헨션 코드
            ids = list(labels)

            current = st.session_state.conversation_id

            # 주의: index 와 key 를 지정하지 않으면 화면을 다시 그릴 때 선택이 풀린다.
            #선택 위젯을 그리고, 사용자가 특정 대화를 선택하면 seleted에 저장한다
            selected = st.selectbox(
                "이전 면접 연습 대화 내역입니다.",
                options = ids,
                format_func = lambda cid : labels[cid],
                index = ids.index(current) if current in ids else 0,
                key = "conversation_select"

            )

            st.session_state.conversation_id = selected
            
            # 기존 대화 제목 변경, 삭제 추가
            new_title = st.text_input("새 이름", key="rename_input")
            rename_column, delete_column = st.columns(2)
            if rename_column.button("이름 변경", use_container_width=True) and new_title:
                api(
                    "PATCH",
                    f"/me/conversations/{selected}",
                    json={"title": new_title},
                    headers=auth_headers(),
                )
                st.rerun()
            if delete_column.button("삭제", use_container_width=True):
                api("DELETE", f"/me/conversations/{selected}", headers=auth_headers())
                st.session_state.conversation_id = None
                st.rerun()
        else:
            st.caption("면접 준비 대화를 시작하세요")
            # 새로운 대화 시작 버튼

        st.divider()

        job_title = st.text_input("면접연습 직무", placeholder='예: AI Agent 개발자')
        # 대화 생성 버튼 클릭 & 직무 입력 확인
        if st.button("새 면접 연습 시작", use_container_width=True) and job_title :
            # 대화 생성 엔드포인트 호출
            created = api(
                                "POST",
                                "/me/conversations",
                                json={"title": job_title},
                                headers=auth_headers(),
                            )

            # 새로 생성한 대화id 를 세션에 저장
            st.session_state.conversation_id = created['id']
            # st.session_state.conversation_select = created['id']
            st.rerun()

        #면접관 설정 영역
        st.divider()
        st.subheader('면접관 타입 설정')
        st.radio("말투", options['tones'], key="tone", horizontal=False)
        st.radio("답변 길이", options['lengths'], key="length", horizontal=True)
        st.caption("설정 값은 새로운 질문부터 적용됩니다.")


            
def render_empty(message: str, hint: str) -> None:
    """빈 화면은 "없다"가 아니라 "다음에 무엇을 하면 되는지"를 말해야 한다."""
    st.info(message)
    st.caption(hint)

# 쳇을 날리는 애
def ask(conversation_id: str, question: str) -> None:
    """질문을 보내고 답을 받는다. 실패하면 화면에 이유를 남긴다."""
    try:
        with st.spinner("면접관이 답변을 준비하는 중..."):
            api(
                "POST",
                f"/conversations/{conversation_id}/chat",
                json={
                    "content": question,
                    "tone": st.session_state.tone,
                    "length": st.session_state.length,
                },
            )
    except ApiError as error:
        st.error(str(error))
        return
    st.rerun() #정상 처리 -> 화면 갱신


#후속 액션 
def render_follow_ups(last_answer: str) -> None:
    """직전 답변을 두고 이어서 할 수 있는 행동.

    주의: 오늘은 모델이 이전 대화를 기억하지 못한다(19일차 주제).
    그래서 직전 답변을 질문 안에 넣어서 보낸다. 맥락은 결국 프롬프트로 들어간다.
    """
    st.caption("이어서")
    actions = {
        "더 자세히": f"방금 한 이 말을 예시를 들어 더 자세히 설명해 주세요.\n\n{last_answer}",
        "간단하게": f"방금 한 이 말을 세 문장으로 줄여 주세요.\n\n{last_answer}",
        "다음 질문": "다음 면접 질문을 하나 주세요.",
    }
    columns = st.columns(len(actions))
    for column, (label, question) in zip(columns, actions.items()):
        if column.button(label, use_container_width=True):
            st.session_state.pending_question = question
            st.rerun()


## 메세지 입력하는 애
def render_conversation(conversation_id: str) -> None:
    """가운데: 주고받은 내용과 입력칸."""

    #메세지 내역 가져오기
    messages = api("GET", f"/conversations/{conversation_id}/messages")

    if not messages:
        render_empty(
            "아직 주고받은 내용이 없습니다.",
            "아래 입력칸에 첫 답변을 적어보세요. 오늘은 저장만 되고, 면접관의 질문은 17일차에 붙입니다.",
        )
        
        #예시 질문 출력
        render_examples(conversation_id)

    #메세지 목록 출력
    for message in messages:
        with st.chat_message(message["role"]):
            st.write(message["content"])

    
    #메세지 목록이 있고, 목록의 마지막 메세지의 role이 assistant일 때만 호출 가능!!
    #제일 마지막에 있는 메세지 꺼내기
    if messages and messages[-1]["role"] == "assistant":
            render_follow_ups(messages[-1]["content"])



    # 버튼을 눌러 세션에 담긴 질문이 있는지 확인 -> 있으면 답변 요청
    if st.session_state.pending_question:
        question = st.session_state.pending_question
        st.session_state.pending_question = None #값 지우지 않음 무한루트 돈다
        ask(conversation_id, question)

    ##############################################################
    ###########################################################3##

    #새로운 메세지 입력 위젯 출력
    if answer := st.chat_input("답변을 입력하세요"):

        ask(conversation_id,answer)

        # 기존에 db에 직접 넣어주던 api 주석 > ask()에서 질문 후 전송해주고있기때문에
        # try:
        #     #입력받은 메세지를 서버 엔드포인트에 전송
        #     api(
        #         "POST",
        #         f"/conversations/{conversation_id}/messages",
        #         json={"role": "user", "content": answer},
        #     )
        # except ApiError as error:
        #     st.error(str(error))
        #     return

        #화면 다시 그리기
        st.rerun()


def render_examples(conversation_id: str) -> None:
    """무엇을 물어야 할지 모르는 사람을 위한 출발점.

    빈 입력칸만 놓아두면 대부분 아무것도 입력하지 않고 나간다.
    """
    st.caption("아래 질문 중 선택해 보세요")
    columns = st.columns(len(EXAMPLE_QUESTIONS))
    #zip : 두개의 값을 하나로 묶어주는 것
    for column, question in zip(columns, EXAMPLE_QUESTIONS):

        #버튼을 클릭하면 질문을 세션 변수에 저장함
        if column.button(question, use_container_width=True):
            st.session_state.pending_question = question
            st.rerun()


def render_login() -> None:
    """비로그인 상태의 화면 - 전체영역"""
    # 1. 세션만료 확인
    if st.session_state.expired_notice:
        st.warning(st.session_state.expired_notice)

    #시작하기 전에 화면에 보여줄 것
    st.write("직무를 정하고 면접 질문에 답하며 연습합니다. 기록은 계정에 저장됩니다.")

    # 2. email, password 입력
    email = st.text_input("이메일", placeholder="you@example.com")
    password = st.text_input("비밀번호", type="password")

    # 3. api / auth/ login, /auth/signup 호출
    #로그인 / 회원가입 버튼 생성
    login_column, signup_column = st.columns(2)
    action = None # 버튼 처리 변수

    #로그인 버튼
    if login_column.button("로그인", use_container_width=True):
        action = "login"

    #회원가입 버튼 
    if signup_column.button("회원가입", use_container_width=True):
        action = "signup"

    # api 호출
    if not action :
        return
    if not email or not password:
        st.error("이메일과 비밀번호를 모두 입력하세요.")
        return
    try:
        result = api(
            "POST", f"/auth/{action}", json={"email": email, "password": password}
        )
    except ApiError as error:
        st.error(str(error))
        return

    if not result.get("access_token"):
        # 가입은 됐는데 토큰이 없는 경우가 있다 (이메일 확인이 켜져 있을 때).
        st.error("가입은 되었지만 바로 로그인되지 않았습니다. 강사에게 알리세요.")
        return

    # 4. 로그인 결과에서 token, email 세션에 저장
    #결과에서 token, email 세션에 저장
    st.session_state.access_token = result["access_token"]
    st.session_state.user_email = result["email"]
    st.session_state.expired_notice = None
    st.rerun()

def sign_out(notice: str | None = None) -> None:
    """로그인 관련 상태를 한 번에 지운다.

    지울 것을 빠뜨리면 다음 사용자에게 앞사람의 대화가 잠깐 보인다.
    그래서 로그아웃과 세션 만료가 같은 함수를 쓰게 해둔다.
    """
    st.session_state.access_token = None
    st.session_state.user_email = None
    st.session_state.conversation_id = None
    st.session_state.pending_question = None
    st.session_state.expired_notice = notice
    st.rerun() #로그인 화면으로 이동

def render_signed_in() -> None:
    """로그인한 뒤의 화면 전체.

    이 안에서 나는 SessionExpired 는 아래 main 이 한 번에 받는다.
    호출마다 try 를 쓰면 스무 군데가 되고, 한 곳만 빠뜨려도
    거기서 화면이 비어 보인다.
    """

    # 브라우저 화면에 렌더링하는 영역 
    # 1. 화면 구성에 필요한 환경정보 설정 - 엔드포인트 호출을 위한
    try:
        options = load_options()
    except ApiError as error:
        st.title(SERVICE_NAME)
        st.error(str(error))
        st.stop()

    # 라디오 버튼의 초기값. 백엔드가 알려준 기본값을 쓴다.
    st.session_state.setdefault("tone", options["default_tone"])
    st.session_state.setdefault("length", options["default_length"])

    #3. 사이드 바 출력
    # 세션의 토큰으로 대화 목록 조회
    conversations = api("GET", "/me/conversations", headers=auth_headers())

    #대화목록으로 사이드바 렌더링
    render_sidebar(options, conversations)

    st.caption(f"말투 {st.session_state.tone} · 길이 {st.session_state.length}")

    if not conversations:
        render_empty(
            "아직 연습 기록이 없습니다.",
            "왼쪽에서 지원할 직무를 적고 `새 면접 시작` 을 누르세요.",
        )
    # 방어 가지. selectbox 가 첫 항목을 자동으로 고르므로 평소에는 닿지 않는다.
    # 목록이 있는데 선택이 비면 render_conversation(None) 이 되어 422 가 난다.
    elif not st.session_state.conversation_id:
        render_empty(
            "연습할 면접을 고르세요.",
            "왼쪽 `지난 연습` 에서 하나를 선택하면 됩니다.",
        )
    else:
        render_conversation(st.session_state.conversation_id)

# 브라우저 화면에 드로임
#화면 구성에 필요한 환경정보 엔드포인트 호출
try:
    options = load_options()
except ApiError as error:
    st.title(SERVICE_NAME)
    st.error(str(error))
    st.stop()

# 라디오 버튼의 초기값. 백엔드가 알려준 기본값을 쓴다.
st.session_state.setdefault("tone", options["default_tone"])
st.session_state.setdefault("length", options["default_length"])

# render_sidebar() ##렌더 잊지말기

st.title(SERVICE_NAME)
# st.caption("직무를 정하고 면접 질문에 답하며 연습합니다.")
# st.caption(f"말투 {st.session_state.tone} · 길이 {st.session_state.length}")

# if not st.session_state.user_id:
#     render_empty(
#         "왼쪽에 user_id 를 입력하세요.",
#         "Supabase SQL Editor 에서 `select id, username from profiles;` 로 확인할 수 있습니다.",
#     )
# elif not st.session_state.conversation_id:
#     render_empty(
#         "연습할 면접을 고르거나 새로 시작하세요.",
#         "왼쪽에서 직무를 적고 `새 면접 시작` 을 누르면 됩니다.",
#     )
# else:
#     render_conversation(st.session_state.conversation_id)

# 로그인한 세션정보가 있을 때 확인
# if st.session_state.access_token:

#     # 세션의 토큰으로 대화 목록 조회
#     conversations = api("GET", "/me/conversations", headers=auth_headers())

#     #대화 목록으로 사이드바 렌더링
#     render_sidebar(options, conversations)

#     st.write(f"{st.session_state.user_email} 로 로그인했습니다.")
# else:
#     render_login()


##화면 생성 영역
try:
    if st.session_state.access_token:
        render_signed_in()
    else:
        render_login()
except SessionExpired as error:
    # 토큰을 지우고 로그인 화면으로 돌린다. 이유는 다음 실행에서 보여준다.
    sign_out(str(error))
except ApiError as error:
    st.error(str(error))

#세션 정보 만료 > sign_out() 