import streamlit as st
from common import ApiError, api, conversation_label,SERVICE_NAME


st.set_page_config(page_title=SERVICE_NAME)


#세션에 사용자id, 대화id를 저장한다.
st.session_state.setdefault("user_id", "")
st.session_state.setdefault("conversation_id", None)


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
                key="conversation_id",
            )
            #세션에 선택한 메세지 아이디 넣어주기
            st.session_state.conversation_id = selected
        else:
            st.caption("아직 연습 기록이 없습니다.")

            


def render_empty(message: str, hint: str) -> None:
    """빈 화면은 "없다"가 아니라 "다음에 무엇을 하면 되는지"를 말해야 한다."""
    st.info(message)
    st.caption(hint)


def render_conversation(conversation_id: str) -> None:
    """가운데: 주고받은 내용과 입력칸."""
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

    for message in messages:
        with st.chat_message(message["role"]):
            st.write(message["content"])

    if answer := st.chat_input("답변을 입력하세요"):
        try:
            api(
                "POST",
                f"/conversations/{conversation_id}/messages",
                json={"role": "user", "content": answer},
            )
        except ApiError as error:
            st.error(str(error))
            return
        st.rerun()


render_sidebar() ##렌더 잊지말기

st.title(SERVICE_NAME)
st.caption("직무를 정하고 면접 질문에 답하며 연습합니다. 오늘은 화면만 만듭니다.")

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
    st.write("(여기에 대화가 들어갑니다 — 실습 8)")



