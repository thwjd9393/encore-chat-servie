import streamlit as st
from common import ApiError, api, conversation_label,SERVICE_NAME


st.set_page_config(page_title=SERVICE_NAME)


#세션에 사용자id, 대화id를 저장한다.
st.session_state.setdefault("user_id", "")
st.session_state.setdefault("conversation_id", None)

# 버튼으로 보낼 질문을 잠시 담아두는 곳. 버튼 안에서 바로 보내면
# 화면이 다시 그려지는 도중이라 결과가 화면에 안 나타난다.
st.session_state.setdefault("pending_question", None)

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


def render_sidebar() -> None:

    with st.sidebar :
        st.subheader("면접 연습용 대화 기록")
        st.text_input( #사용자 아이디 받는부분
            "사용자 ID(Profiles 테이블의 ID)", key="user_id"
        )
        if not st.session_state.user_id : #사용자 정보가 없을 때
            st.caption("user_id 를 입력하면 연습 기록이 나타납니다.")
            # 더이상 진행하지 않는다
            return

        try:
            conversations = api( #대화 목록 가져오는 곳
                "GET", "/conversations", params={"user_id": st.session_state.user_id}
            )
        except ApiError as error: #대화가 없을 떄
            st.error(str(error))
            return

        if conversations: #대화가 있을 떄 -> 보기좋게 한줄로 만들어주기
            labels = {c["id"]: conversation_label(c) for c in conversations}
            ids = list(labels)

            # 주의: index 와 key 를 지정하지 않으면 화면을 다시 그릴 때 선택이 풀린다.
            #선택 위젯을 그리고, 사용자가 특정 대화를 선택하면 seleted에 저장한다
            selected = st.selectbox(
                "이전 면접 연습 기록이 없습니다",
                options=ids,
                format_func=lambda cid: labels[cid],
                key="conversation_select",
            )
            #세션에 선택한 메세지 아이디 넣어주기
            st.session_state.conversation_id = selected
        else:
            st.caption("아직 연습 기록이 없습니다.")

        st.divider() #선

        job_title = st.text_input("직무", placeholder="예: 백엔드 개발자")
        #잡타이틀이 있냐 없냐에 따라 true/false가 됨
        if st.button("새 면접 시작", use_container_width=True) and job_title: 
            try:
                created = api(
                    "POST",
                    "/conversations",
                    json={"user_id": st.session_state.user_id, "title": job_title},
                )
            except ApiError as error:
                st.error(str(error))
                return

            #새로 생성한 대화 id를 세션에 저장
            st.session_state.conversation_id = created["id"]
            st.rerun()


        #면접관과 톤 길이 설정하는 라디오 버튼
        st.divider()
        st.subheader("면접관 설정")
        # 이 두 값이 곧 프롬프트의 두 문장이 된다.
        st.radio("말투", options["tones"], key="tone", horizontal=True)
        st.radio("답변 길이", options["lengths"], key="length", horizontal=True)
        st.caption("고른 값은 다음 질문부터 적용됩니다. 이미 받은 답변은 바뀌지 않습니다.")

            
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
    try:
        messages = api("GET", f"/conversations/{conversation_id}/messages")
    except ApiError as error:
        st.error(str(error))
        return

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

render_sidebar() ##렌더 잊지말기

st.title(SERVICE_NAME)
st.caption("직무를 정하고 면접 질문에 답하며 연습합니다.")
st.caption(f"말투 {st.session_state.tone} · 길이 {st.session_state.length}")

if not st.session_state.user_id:
    render_empty(
        "왼쪽에 user_id 를 입력하세요.",
        "Supabase SQL Editor 에서 `select id, username from profiles;` 로 확인할 수 있습니다.",
    )
elif not st.session_state.conversation_id:
    render_empty(
        "연습할 면접을 고르거나 새로 시작하세요.",
        "왼쪽에서 직무를 적고 `새 면접 시작` 을 누르면 됩니다.",
    )
else:
    render_conversation(st.session_state.conversation_id)



