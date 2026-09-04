import streamlit as st


from common import (
    ApiError,
    SERVICE_NAME,
    SessionExpired,
    api,
    auth_headers,
    conversation_label,
    stream_answer,
)


"""20일차 완성본 — 실시간 응답과 피드백 UX.

18일차에는 로그인과 사용자 상태를 화면에서 처리했고,
19일차에는 이전 대화를 모델에게 전달해서 대화 맥락을 기억하게 만들었다.

20일차에는 사용자가 실제 서비스를 사용할 때 발생하는 상황을 처리한다.


사용자가 겪는 것        화면이 하는 일
--------------------   --------------------------------
답이 늦다               글자가 나오는 대로 흘려보낸다
답을 못 받았다           같은 질문으로 `다시 시도`
답이 마음에 안 든다       기존 답을 지우고 `다시 생성`
답이 좋았다/아쉬웠다      `도움됨` / `아쉬움` 을 남긴다


`다시 시도`와 `다시 생성`은 다르다.

다시 시도
-> 요청 자체가 실패해서 답변을 받지 못한 경우
-> 실패했던 질문을 그대로 다시 보낸다.

다시 생성
-> 답변은 정상적으로 받았지만 결과가 마음에 들지 않는 경우
-> 기존 assistant 답변을 지우고 같은 질문으로 새 답변을 만든다.
"""


# ---------------------------------------------------------
# 페이지 설정
# ---------------------------------------------------------

st.set_page_config(
    page_title=SERVICE_NAME,
    layout="centered",
)


# ---------------------------------------------------------
# 세션 상태 초기화
# ---------------------------------------------------------

# 세션에 사용자id, 대화id를 저장한다.

# 17일차까지는 user_id를 직접 입력해서 사용했음.
# 18일차부터는 로그인한 사용자의 토큰을 사용하기 때문에 필요 없음.
# st.session_state.setdefault("user_id", "")


# RLS 적용한 /me 라우터용
# 로그인 성공 후 백엔드에서 받은 access_token 저장
st.session_state.setdefault("access_token", None)

# 로그인한 사용자 이메일
st.session_state.setdefault("user_email", None)

# 현재 선택된 대화 id
st.session_state.setdefault("conversation_id", None)


# 버튼으로 보낼 질문을 잠시 담아두는 곳.
# 버튼 안에서 바로 보내면 화면이 다시 그려지는 도중이라
# 결과가 화면에 안 나타날 수 있다.
st.session_state.setdefault("pending_question", None)


# 세션이 풀린 이유를 다음 실행에서 보여주려고 남겨둔다.
# 토큰만 지우고 끝내면 사용자는 자기가 왜 로그아웃됐는지 모른다.
st.session_state.setdefault("expired_notice", None)


# ---------------------------------------------------------
# 스트리밍 실패 복구용 상태
# ---------------------------------------------------------

# 답변을 받지 못한 질문을 저장한다.
#
# API 호출이 실패했을 때 사용자가 같은 질문을
# 다시 입력하지 않아도 `다시 시도` 버튼으로
# 그대로 다시 전송할 수 있게 한다.
st.session_state.setdefault("failed_question", None)


# ---------------------------------------------------------
# 예시 질문
# ---------------------------------------------------------

EXAMPLE_QUESTIONS = [
    "면접을 시작해 주세요.",
    "1분 자기소개를 해보겠습니다.",
    "제 이력서에서 가장 많이 받을 질문이 뭘까요?",
]


# =========================================================
# 모델이 현재 기억하는 메시지 개수 계산
#
# 전체 DB 메시지 개수를 세는 것이 아니다.
#
# 1. 마지막 system 메시지 이후의 대화만 사용
# 2. user / assistant 메시지만 사용
# 3. 백엔드 MAX_HISTORY_MESSAGES 제한 적용
#
# 즉 백엔드의 _build_history()가 Gemini에게 보내는
# 실제 메시지 개수와 같은 기준으로 계산한다.
# =========================================================

def _remembered_count(
    messages: list,
    max_history: int,
) -> int:

    """모델에게 실제로 갈 메시지 수.

    백엔드 _build_history 와 같은 순서로 센다.
    """

    # 가장 최근 system 메시지를 뒤에서부터 찾는다.
    #
    # system 메시지는
    # "여기부터 이전 맥락을 끊었다"
    # 라는 의미로 사용하고 있다.
    for index in range(
        len(messages) - 1,
        -1,
        -1,
    ):

        if messages[index]["role"] == "system":

            # system 메시지 다음부터만 기억 대상으로 사용
            messages = messages[index + 1 :]

            break


    # user / assistant 메시지만 실제 대화 맥락으로 사용
    usable = [
        m
        for m in messages
        if m["role"] in (
            "user",
            "assistant",
        )
    ]


    # 실제 메시지 수와
    # 최대 기억 개수 중 작은 값을 반환한다.
    #
    # 예:
    #
    # 실제 메시지 7개
    # 최대 기억 20개
    # -> 7
    #
    # 실제 메시지 31개
    # 최대 기억 20개
    # -> 20
    return min(
        len(usable),
        max_history,
    )


# ---------------------------------------------------------
# 백엔드 옵션 가져오기
# ---------------------------------------------------------

@st.cache_data(ttl=300)
def load_options() -> dict:

    """선택지는 백엔드에서 받아온다.

    화면에 목록을 직접 적어두면
    백엔드의 표와 두 곳에서 관리하게 된다.

    한쪽에 톤을 추가하고 다른 쪽을 잊으면,
    버튼은 있는데 아무 효과가 없다.


    ttl=300

    -> 받아온 값을 300초(5분) 동안
       캐시에 저장한다.
    """

    return api(
        "GET",
        "/chat/options",
    )


# ---------------------------------------------------------
# 로그아웃 / 세션 만료 처리
# ---------------------------------------------------------

def sign_out(
    notice: str | None = None,
) -> None:

    """로그인 관련 상태를 한 번에 지운다.

    지울 것을 빠뜨리면
    다음 사용자에게 앞사람의 대화가
    잠깐 보일 수 있다.

    그래서 일반 로그아웃과 세션 만료가
    같은 함수를 사용하게 해둔다.
    """


    # 로그인 토큰 제거
    st.session_state.access_token = None


    # 로그인 사용자 이메일 제거
    st.session_state.user_email = None


    # 현재 선택 대화 제거
    st.session_state.conversation_id = None


    # 버튼으로 예약된 질문 제거
    st.session_state.pending_question = None


    # 답을 못 받은 질문 제거
    st.session_state.failed_question = None


    # 세션 만료라면 이유를 저장한다.
    #
    # 일반 로그아웃이면 notice=None
    st.session_state.expired_notice = notice


    # 로그인 화면으로 이동
    st.rerun()


# ---------------------------------------------------------
# 로그인 / 회원가입 화면
# ---------------------------------------------------------

def render_login() -> None:

    """비로그인 상태의 화면 - 전체영역."""


    # -----------------------------------------------------
    # 1. 세션 만료 확인
    # -----------------------------------------------------

    if st.session_state.expired_notice:

        st.warning(
            st.session_state.expired_notice
        )


    # 시작하기 전에 화면에 보여줄 것
    st.write(
        "직무를 정하고 면접 질문에 답하며 연습합니다. "
        "기록은 계정에 저장됩니다."
    )


    # -----------------------------------------------------
    # 2. email, password 입력
    # -----------------------------------------------------

    email = st.text_input(
        "이메일",
        placeholder="you@example.com",
    )


    password = st.text_input(
        "비밀번호",
        type="password",
    )


    # -----------------------------------------------------
    # 3. api /auth/login, /auth/signup 호출
    # -----------------------------------------------------

    # 로그인 / 회원가입 버튼 생성
    login_column, signup_column = st.columns(2)


    # 버튼 처리 변수
    action = None


    # 로그인 버튼
    if login_column.button(
        "로그인",
        use_container_width=True,
    ):

        action = "login"


    # 회원가입 버튼
    if signup_column.button(
        "회원가입",
        use_container_width=True,
    ):

        action = "signup"


    # 아무 버튼도 클릭하지 않았다면
    # 여기서 종료
    if not action:

        return


    # 이메일 또는 비밀번호가 비어있을 때
    if not email or not password:

        st.error(
            "이메일과 비밀번호를 모두 입력하세요."
        )

        return


    # 로그인 / 회원가입 API 호출
    try:

        result = api(
            "POST",
            f"/auth/{action}",
            json={
                "email": email,
                "password": password,
            },
        )


    except ApiError as error:

        st.error(
            str(error)
        )

        return


    # 가입은 됐는데 토큰이 없는 경우가 있다.
    #
    # Supabase에서 이메일 확인 기능이
    # 켜져 있을 때 발생할 수 있음.
    if not result.get(
        "access_token"
    ):

        st.error(
            "가입은 되었지만 바로 로그인되지 않았습니다. "
            "강사에게 알리세요."
        )

        return


    # -----------------------------------------------------
    # 4. 로그인 결과에서 token, email 세션에 저장
    # -----------------------------------------------------

    st.session_state.access_token = (
        result["access_token"]
    )


    st.session_state.user_email = (
        result["email"]
    )


    # 이전에 세션 만료 메시지가 있었다면 제거
    st.session_state.expired_notice = None


    # 로그인 상태로 화면 다시 그리기
    st.rerun()


# ---------------------------------------------------------
# 사이드바
# ---------------------------------------------------------

def render_sidebar(
    options: dict,
    conversations: list,
) -> None:


    with st.sidebar:


        st.subheader(
            "면접 연습용 대화 기록"
        )


        # 로그인한 사용자 이메일
        st.caption(
            st.session_state.user_email
        )


        # -------------------------------------------------
        # 로그아웃
        # -------------------------------------------------

        if st.button(
            "로그아웃",
            use_container_width=True,
        ):

            sign_out()


        # -------------------------------------------------
        # 예전 방식
        # -------------------------------------------------

        # 17일차까지는 사용자가 user_id를
        # 직접 입력했음.
        #
        # st.text_input(
        #     "사용자 ID(Profiles 테이블의 ID)",
        #     key="user_id"
        # )
        #
        # if not st.session_state.user_id:
        #
        #     st.caption(
        #         "user_id 를 입력하면 "
        #         "연습 기록이 나타납니다."
        #     )
        #
        #     return


        st.divider()


        st.subheader(
            "연습 기록"
        )


        # -------------------------------------------------
        # 예전 대화 목록 조회 방식
        # -------------------------------------------------

        # try:
        #
        #     conversations = api(
        #         "GET",
        #         "/conversations",
        #         params={
        #             "user_id":
        #             st.session_state.user_id
        #         }
        #     )
        #
        # except ApiError as error:
        #
        #     st.error(str(error))
        #
        #     return


        # -------------------------------------------------
        # 대화가 있을 때
        # -------------------------------------------------

        if conversations:


            # 대화 목록을
            #
            # {
            #     대화ID: 화면에 보여줄 이름
            # }
            #
            # 형태로 만들어준다.

            labels = {
                c["id"]:
                conversation_label(c)
                for c in conversations
            }


            ids = list(
                labels
            )


            # 현재 선택된 대화
            current = (
                st.session_state.conversation_id
            )


            # -------------------------------------------------
            # 지난 연습 선택
            # -------------------------------------------------

            # 주의:
            #
            # index와 key를 지정하지 않으면
            # 화면을 다시 그릴 때
            # 선택이 풀릴 수 있다.
            #
            # 선택 위젯을 그리고
            # 사용자가 특정 대화를 선택하면
            # selected에 저장한다.

            selected = st.selectbox(
                "이전 면접 연습 대화 내역입니다.",
                options=ids,


                # DB의 id 대신
                # 보기 좋은 제목 출력
                format_func=lambda cid: labels[cid],


                # 기존에 선택한 대화가 있으면
                # 그것을 유지
                index=(
                    ids.index(current)
                    if current in ids
                    else 0
                ),


                key="conversation_select",
            )


            # 선택한 대화를 세션에 저장
            st.session_state.conversation_id = (
                selected
            )


            # -------------------------------------------------
            # 기존 대화 제목 변경 / 삭제
            # -------------------------------------------------

            new_title = st.text_input(
                "새 이름",
                key="rename_input",
            )


            rename_column, delete_column = (
                st.columns(2)
            )


            # 이름 변경
            if (
                rename_column.button(
                    "이름 변경",
                    use_container_width=True,
                )
                and new_title
            ):

                api(
                    "PATCH",
                    f"/me/conversations/{selected}",
                    json={
                        "title": new_title
                    },
                    headers=auth_headers(),
                )


                st.rerun()


            # 삭제
            if delete_column.button(
                "삭제",
                use_container_width=True,
            ):

                api(
                    "DELETE",
                    f"/me/conversations/{selected}",
                    headers=auth_headers(),
                )


                # 삭제한 대화를
                # 선택 상태에서 제거
                st.session_state.conversation_id = (
                    None
                )


                st.rerun()


        else:

            # 아직 대화가 없는 사용자
            st.caption(
                "아직 연습 기록이 없습니다."
            )


        # -------------------------------------------------
        # 새로운 면접 시작
        # -------------------------------------------------

        st.divider()


        job_title = st.text_input(
            "면접연습 직무",
            placeholder="예: AI Agent 개발자",
        )


        # 대화 생성 버튼 클릭
        # &
        # 직무 입력 확인

        if (
            st.button(
                "새 면접 연습 시작",
                use_container_width=True,
            )
            and job_title
        ):


            # -------------------------------------------------
            # 대화 생성 엔드포인트 호출
            # -------------------------------------------------

            # 주의:
            #
            # 이제 user_id를
            # 클라이언트가 보내지 않는다.
            #
            # 서버가 access_token을 확인하고
            # 토큰에서 로그인 사용자의 id를 꺼낸다.

            created = api(
                "POST",
                "/me/conversations",

                json={
                    "title": job_title
                },

                headers=auth_headers(),
            )


            # 새로 생성한 대화 id를
            # 세션에 저장
            st.session_state.conversation_id = (
                created["id"]
            )


            # 아래처럼 selectbox 상태를
            # 직접 변경할 필요 없음
            #
            # st.session_state.conversation_select
            # = created["id"]


            st.rerun()


        # -------------------------------------------------
        # 면접관 설정 영역
        # -------------------------------------------------

        st.divider()


        st.subheader(
            "면접관 타입 설정"
        )


        st.radio(
            "말투",
            options["tones"],
            key="tone",
            horizontal=False,
        )


        st.radio(
            "답변 길이",
            options["lengths"],
            key="length",
            horizontal=True,
        )


        st.caption(
            "설정 값은 새로운 질문부터 적용됩니다."
        )


# ---------------------------------------------------------
# 빈 화면 안내
# ---------------------------------------------------------

def render_empty(
    message: str,
    hint: str,
) -> None:

    """빈 화면은 '없다'가 아니라

    '다음에 무엇을 하면 되는지'

    를 말해야 한다.
    """

    st.info(
        message
    )


    st.caption(
        hint
    )


# ---------------------------------------------------------
# 질문 전송
# ---------------------------------------------------------

# 챗을 날리는 애
#
# 기존
# -> 실시간 반응 전
# -> api 직접 불러서 사용


# ---------------------------------------------------------
# 이전 방식
# ---------------------------------------------------------

# def ask(
#     conversation_id: str,
#     question: str,
# ) -> None:
#
#     """질문을 서버에 보내고 AI의 답변을 받는다.
#
#     여기서는 ApiError / SessionExpired를
#     잡지 않는다.
#
#     이유:
#
#     SessionExpired를 화면 최하단 main 영역에서
#     한 번에 처리하기 위해서다.
#
#     각각의 API 호출에서 try/except를 작성하면
#     API 호출이 많아질수록
#     세션 만료 처리를 빼먹을 가능성이 커진다.
#     """
#
#     with st.spinner(
#         "면접관이 답변을 준비하는 중..."
#     ):
#
#         api(
#             "POST",
#             f"/conversations/{conversation_id}/chat",
#             json={
#                 "content": question,
#                 "tone": st.session_state.tone,
#                 "length": st.session_state.length,
#             },
#         )
#
#     st.rerun()


# ---------------------------------------------------------
# 현재 방식
# stream_answer 함수를 사용해
# AI가 만든 글자를 실시간으로 출력한다.
# ---------------------------------------------------------

def ask(
    conversation_id: str,
    question: str,
) -> None:

    """질문을 보내고 답이 흘러나오는 것을 보여준다.

    19일차까지는 답변이 전부 만들어진 뒤
    화면을 새로 그렸다.

    그래서 몇 초 동안
    아무 일도 일어나지 않는 것처럼 보였다.

    오늘은 글자가 만들어지는 대로 보여준다.
    """


    # 사용자가 방금 입력한 질문을
    # 바로 화면에 보여준다.
    with st.chat_message(
        "user"
    ):

        st.write(
            question
        )


    # AI 답변 영역
    with st.chat_message(
        "assistant"
    ):


        try:

            # st.write_stream 은
            # generator가 넘겨주는 문자열 조각을 받아서
            # 화면에 계속 이어 붙인다.
            #
            # 그래서 AI 답변이 완성될 때까지
            # 기다렸다가 한 번에 보여주는 게 아니라
            # 만들어지는 즉시 볼 수 있다.

            st.write_stream(

                stream_answer(

                    f"/conversations/{conversation_id}/chat",

                    {
                        "content": question,
                        "tone": st.session_state.tone,
                        "length": st.session_state.length,
                    },
                )
            )


        except ApiError as error:


            # 실패한 질문을 기억해 둔다.
            #
            # `다시 시도` 버튼이 이것을 쓴다.
            #
            # 사용자가 긴 답변을 다시
            # 타이핑하게 만들면 안 된다.

            st.session_state.failed_question = (
                question
            )


            st.error(
                str(error)
            )


            return


    # 정상적으로 답을 받았으면
    # 실패 질문 상태를 제거한다.
    st.session_state.failed_question = None


    # DB에는 user / assistant 메시지가
    # 저장되어 있으므로 화면을 다시 그린다.
    st.rerun()


# ---------------------------------------------------------
# 다시 생성
# ---------------------------------------------------------

def regenerate(
    conversation_id: str,
) -> None:

    """마지막 답변을 지우고 새로 받는다.

    다시 시도(Retry)와 다르다.


    다시 시도

    -> 요청 자체가 실패했다.
    -> 아직 AI 답변이 없는 상태다.
    -> 실패했던 질문을 그대로 다시 보낸다.


    다시 생성

    -> 요청은 성공했다.
    -> AI 답변도 이미 있다.
    -> 하지만 결과가 마음에 들지 않는다.
    -> 기존 AI 답변을 지우고 다시 생성한다.
    """


    with st.chat_message(
        "assistant"
    ):


        try:

            st.write_stream(

                stream_answer(

                    f"/conversations/{conversation_id}/regenerate",


                    # 질문은 다시 보내지 않는다.
                    #
                    # 서버가 DB에서
                    # 마지막 user 질문을 찾아서 사용한다.
                    #
                    # 사용자는 다시 생성하기 전에
                    # 말투 / 길이를 바꿀 수도 있기 때문에
                    # 현재 설정값만 보낸다.

                    {
                        "tone": st.session_state.tone,
                        "length": st.session_state.length,
                    },
                )
            )


        except ApiError as error:


            st.error(
                str(error)
            )


            return


    # 새로 생성된 답변이 DB에 저장됐으므로
    # 화면을 다시 그린다.
    st.rerun()


# ---------------------------------------------------------
# 예시 질문
# ---------------------------------------------------------

def render_examples() -> None:

    """무엇을 물어야 할지 모르는 사람을 위한 출발점.

    빈 입력칸만 놓아두면
    대부분 아무것도 입력하지 않고
    나갈 수 있다.
    """


    st.caption(
        "아래 질문 중 선택해 보세요"
    )


    columns = st.columns(
        len(EXAMPLE_QUESTIONS)
    )


    # zip:
    #
    # 두 개의 값을 하나씩 묶어주는 것
    #
    # column1 + question1
    # column2 + question2
    # column3 + question3

    for column, question in zip(
        columns,
        EXAMPLE_QUESTIONS,
    ):


        # 버튼을 클릭하면
        # 질문을 세션 변수에 저장함
        if column.button(
            question,
            use_container_width=True,
        ):


            st.session_state.pending_question = (
                question
            )


            st.rerun()


# ---------------------------------------------------------
# 후속 액션
# ---------------------------------------------------------

def render_follow_ups() -> None:

    """직전 답변을 두고 이어서 할 수 있는 행동.

    17·18일차에는
    직전 답변을 질문 안에 통째로 넣어 보냈다.

    하지만 현재는 백엔드의 _build_history()가
    이전 user / assistant 대화를 Gemini에게 전달한다.

    따라서 이제는 직전 답변을
    다시 질문 안에 복사해서 넣을 필요가 없다.

    "방금"이라고만 해도
    모델은 이전 대화를 참고할 수 있다.
    """


    st.caption(
        "이어서"
    )


    actions = {

        "더 자세히":
        "방금 한 말을 예시를 들어 "
        "더 자세히 설명해 주세요.",

        "간단하게":
        "방금 한 말을 세 문장으로 "
        "줄여 주세요.",

        "다음 질문":
        "다음 면접 질문을 하나 주세요.",
    }


    columns = st.columns(
        len(actions)
    )


    for column, (
        label,
        question,
    ) in zip(

        columns,
        actions.items(),
    ):


        if column.button(
            label,
            use_container_width=True,
        ):


            st.session_state.pending_question = (
                question
            )


            st.rerun()


# ---------------------------------------------------------
# 초기화 버튼
# &
# 현재 기억하고 있는 메시지 개수
# ---------------------------------------------------------

def render_context_controls(
    conversation_id: str,
    messages: list,
    max_history: int,
) -> None:

    """면접관이 무엇을 기억하는지 보여주고,
    끊을 수 있게 한다.

    사용자는 모델이 무엇을 참고하는지 볼 수 없다.

    화면이 말해주지 않으면

    "왜 아까 한 말을 기억 못하지"

    또는 반대로

    "왜 지운 얘기를 계속 하지"

    가 된다.
    """


    # 백엔드에서 모델에게 실제로 전달될
    # 메시지 개수 계산
    remembered = _remembered_count(
        messages,
        max_history,
    )


    # 버튼 영역 / 설명 영역
    reset_column, info_column = st.columns(
        [1, 3]
    )


    # 맥락 초기화
    if reset_column.button(
        "맥락 초기화",
        use_container_width=True,
    ):


        api(
            "POST",
            f"/conversations/{conversation_id}/reset-context",
        )


        st.rerun()


    # 현재 모델이 기억하는 메시지 개수 안내
    info_column.caption(

        f"면접관은 지금 이 대화의 "
        f"최근 {remembered}개를 기억합니다 "

        f"(최대 {max_history}개). "

        f"초기화해도 기록은 남습니다."
    )


# ---------------------------------------------------------
# 피드백 버튼
# ---------------------------------------------------------

def render_feedback(
    conversation_id: str,
    message_id: str,
    current: str | None,
) -> None:

    """이 답변이 도움이 됐는지 묻는다.

    이미 누른 것은 눌린 상태로 보여야 한다.

    그렇지 않으면 사용자가
    자기가 평가했는지 기억하지 못하고
    계속 다시 누를 수 있다.
    """


    # 도움됨 / 아쉬움 / 빈 공간
    up_column, down_column, _ = st.columns(
        [1, 1, 8]
    )


    # -----------------------------------------------------
    # 도움됨
    # -----------------------------------------------------

    up_column.button(

        "도움됨",

        # message마다 서로 다른 버튼이어야 하므로
        # message_id를 key에 사용한다.
        key=f"up_{message_id}",


        # 현재 선택값이 up이면
        # primary 버튼으로 강조한다.
        type=(
            "primary"
            if current == "up"
            else "secondary"
        ),


        # 버튼이 눌렸을 때 실행할 함수
        on_click=_toggle_feedback,


        # _toggle_feedback 함수에 전달할 값
        args=(
            conversation_id,
            message_id,
            "up",
            current,
        ),
    )


    # -----------------------------------------------------
    # 아쉬움
    # -----------------------------------------------------

    down_column.button(

        "아쉬움",

        key=f"down_{message_id}",


        type=(
            "primary"
            if current == "down"
            else "secondary"
        ),


        on_click=_toggle_feedback,


        args=(
            conversation_id,
            message_id,
            "down",
            current,
        ),
    )


# ---------------------------------------------------------
# 피드백 저장 / 취소
# ---------------------------------------------------------

def _toggle_feedback(
    conversation_id: str,
    message_id: str,
    value: str,
    current: str | None,
) -> None:


    # 같은 것을 다시 누르면 취소다.
    #
    # 잘못 누른 것을 되돌릴 수 없으면 안 된다.
    #
    # 예:
    #
    # 현재 값 = "up"
    # 다시 도움됨 클릭
    #
    # -> value=None
    #
    # 현재 값 = None
    # 도움됨 클릭
    #
    # -> value="up"

    api(
        "POST",

        f"/conversations/{conversation_id}/feedback",

        json={

            "message_id":
            message_id,


            "value": (
                None
                if current == value
                else value
            ),
        },
    )


# ---------------------------------------------------------
# 대화 화면
# ---------------------------------------------------------

# 메시지 입력하는 애

def render_conversation(
    conversation_id: str,
    max_history: int,
) -> None:

    """가운데:

    주고받은 내용과 입력칸.
    """


    # -----------------------------------------------------
    # 메시지 내역 가져오기
    # -----------------------------------------------------

    messages = api(
        "GET",
        f"/conversations/{conversation_id}/messages",
    )


    # -----------------------------------------------------
    # AI 답변 피드백 가져오기
    # -----------------------------------------------------

    # 예:
    #
    # {
    #     "메시지ID1": "up",
    #     "메시지ID2": "down"
    # }
    #
    # 아직 피드백이 하나도 없다면
    # None일 수도 있기 때문에
    # `or {}` 로 빈 딕셔너리로 바꿔준다.

    feedback = api(
        "GET",
        f"/conversations/{conversation_id}/feedback",
    ) or {}


    # -----------------------------------------------------
    # 메시지가 하나도 없는 경우
    # -----------------------------------------------------

    if not messages:


        render_empty(

            "아직 주고받은 내용이 없습니다.",

            "아래 예시를 누르거나 직접 입력해서 "
            "면접을 시작하세요.",
        )


        # 예시 질문 출력
        render_examples()


    # -----------------------------------------------------
    # 메시지 목록 출력
    # -----------------------------------------------------

    # 마지막 메시지의 위치를 기억한다.
    #
    # 다시 생성 버튼은
    # 마지막 AI 답변에만 보여준다.
    #
    # 중간 AI 답변을 다시 만들어버리면
    # 그 이후의 대화와 앞뒤가
    # 맞지 않게 되기 때문이다.

    last_index = (
        len(messages) - 1
    )


    # 기존:
    #
    # for message in messages:
    #
    # 메시지 내용만 필요했다.
    #
    # 이제는 현재 메시지가
    # 몇 번째인지 알아야 한다.
    #
    # 그래서 enumerate() 사용
    #
    # index
    # -> 현재 메시지 위치
    #
    # message
    # -> 실제 메시지 데이터

    for index, message in enumerate(
        messages
    ):


        # -------------------------------------------------
        # system 메시지
        # -------------------------------------------------

        if message["role"] == "system":


            # 맥락을 끊은 지점.
            #
            # 말풍선이 아니라
            # 구분선으로 그린다.
            #
            # 누가 한 말이 아니라
            # "여기서 맥락이 끊겼다"
            # 라는 표시이기 때문이다.

            st.divider()


            st.caption(
                message["content"]
            )


            continue


        # -------------------------------------------------
        # user / assistant 메시지
        # -------------------------------------------------

        # with:
        #
        # 특정 작업을 하는 동안 사용할
        # "문맥(context)"을 열어주는 문법
        #
        # with 컨테이너:
        #     화면에_그릴것()
        #
        # 아래 코드는 message["role"]에 따라
        #
        # user 말풍선
        # 또는
        # assistant 말풍선
        #
        # 안에 내용을 그린다.

        with st.chat_message(
            message["role"]
        ):


            st.write(
                message["content"]
            )


            # ---------------------------------------------
            # AI 답변일 때
            # ---------------------------------------------

            if message["role"] == "assistant":


                # AI 답변에만
                # 도움됨 / 아쉬움 버튼을 보여준다.
                #
                # 사용자가 작성한 메시지에는
                # 평가 버튼이 필요하지 않다.

                render_feedback(

                    conversation_id,

                    message["id"],


                    # 해당 메시지에
                    # 이미 피드백이 있으면
                    #
                    # "up"
                    # 또는
                    # "down"
                    #
                    # 없다면 None
                    feedback.get(
                        message["id"]
                    ),
                )


                # -----------------------------------------
                # 마지막 AI 답변일 때만
                # 다시 생성
                # -----------------------------------------

                if index == last_index:


                    # 다시 생성은
                    # 마지막 답변에만 붙인다.
                    #
                    # 중간 답변을 다시 만들면
                    # 그 뒤 대화와
                    # 앞뒤가 맞지 않게 된다.

                    if st.button(

                        "다시 생성",

                        key=(
                            f"regen_{message['id']}"
                        ),
                    ):


                        regenerate(
                            conversation_id
                        )


    # -----------------------------------------------------
    # 답변을 받지 못한 경우
    # -----------------------------------------------------

    # ask()에서 API 오류가 발생하면
    #
    # st.session_state.failed_question
    #
    # 에 실패한 질문이 저장되어 있다.

    if st.session_state.failed_question:


        # 답을 못 받은 상태다.
        #
        # 같은 질문을 그대로
        # 다시 보낼 수 있게 한다.

        st.warning(
            "답변을 받지 못했습니다."
        )


        retry_column, cancel_column, _ = (
            st.columns(
                [1, 1, 6]
            )
        )


        # -------------------------------------------------
        # 다시 시도
        # -------------------------------------------------

        if retry_column.button(
            "다시 시도"
        ):


            # 실패했던 질문을 꺼낸다.
            question = (
                st.session_state.failed_question
            )


            # 먼저 상태를 지운다.
            #
            # 지우지 않고 ask()를 호출하면
            # rerun 과정에서 다시 처리될 수 있다.
            st.session_state.failed_question = None


            # 같은 질문을 다시 전송
            ask(
                conversation_id,
                question,
            )


        # -------------------------------------------------
        # 취소
        # -------------------------------------------------

        if cancel_column.button(
            "취소"
        ):


            # 실패했던 질문을 버린다.
            st.session_state.failed_question = None


            st.rerun()


    # -----------------------------------------------------
    # 맥락 초기화 / 기억 메시지 수
    # -----------------------------------------------------

    # 메시지가 하나도 없는데
    #
    # "최근 0개를 기억합니다"
    #
    # 또는
    #
    # "맥락 초기화"
    #
    # 버튼을 보여줄 필요는 없다.
    #
    # 따라서 메시지가 있을 때만 표시한다.

    if messages:

        render_context_controls(

            conversation_id,

            messages=messages,

            max_history=max_history,
        )


    # -----------------------------------------------------
    # 후속 질문
    # -----------------------------------------------------

    # 메시지 목록이 있고
    #
    # 목록의 마지막 메시지 role이
    # assistant일 때만 호출 가능
    #
    # 즉 AI가 답변을 끝낸 뒤에만
    #
    # 더 자세히
    # 간단하게
    # 다음 질문
    #
    # 버튼을 보여준다.


    # -----------------------------------------------------
    # 예전 방식
    # -----------------------------------------------------

    # if (
    #     messages
    #     and messages[-1]["role"] == "assistant"
    # ):
    #
    #     render_follow_ups(
    #         messages[-1]["content"]
    #     )


    # -----------------------------------------------------
    # 현재 방식
    # -----------------------------------------------------

    # 메시지를 기억하는 코드로 바꿨기 때문에
    # 마지막 assistant 메시지의 내용을
    # 직접 함수에 넘길 필요가 없다.
    #
    # 백엔드 _build_history()가
    # 이전 대화를 Gemini에게 전달한다.

    if (
        messages
        and messages[-1]["role"] == "assistant"
    ):


        render_follow_ups()


    # -----------------------------------------------------
    # 예시 / 후속 버튼으로 입력된 질문 처리
    # -----------------------------------------------------

    # 버튼을 눌러
    # 세션에 담긴 질문이 있는지 확인
    #
    # -> 있으면 답변 요청

    if st.session_state.pending_question:


        question = (
            st.session_state.pending_question
        )


        # 값을 지우지 않으면
        # 화면이 rerun될 때 계속 질문을 보내서
        # 무한 루프가 발생한다.

        st.session_state.pending_question = None


        ask(
            conversation_id,
            question,
        )


    ##############################################################
    ##############################################################


    # -----------------------------------------------------
    # 새로운 메시지 입력 위젯 출력
    # -----------------------------------------------------

    if answer := st.chat_input(
        "답변을 입력하세요"
    ):


        ask(
            conversation_id,
            answer,
        )


        # -------------------------------------------------
        # 기존에 DB에 직접 메시지를 넣어주던 API
        # -------------------------------------------------

        # 이제는 ask()에서
        #
        # 사용자 질문 저장
        # +
        # AI 호출
        # +
        # AI 답변 저장
        #
        # 을 백엔드에서 처리하기 때문에
        # 아래 코드는 필요 없다.


        # try:
        #
        #     api(
        #         "POST",
        #         f"/conversations/{conversation_id}/messages",
        #
        #         json={
        #             "role": "user",
        #             "content": answer
        #         },
        #     )
        #
        #
        # except ApiError as error:
        #
        #     st.error(
        #         str(error)
        #     )
        #
        #     return


        # ask() 함수 안에서
        # 이미 st.rerun()을 실행한다.
        #
        # 따라서 여기에서
        # 다시 st.rerun()할 필요 없음.

        # st.rerun()


# ---------------------------------------------------------
# 로그인 이후 전체 화면
# ---------------------------------------------------------

def render_signed_in() -> None:

    """로그인한 뒤의 화면 전체.

    이 안에서 나는 SessionExpired는
    아래 main 영역이 한 번에 받는다.

    호출마다 try를 쓰면 스무 군데가 되고,
    한 곳만 빠뜨려도
    거기서 화면이 비어 보인다.
    """


    # -----------------------------------------------------
    # 브라우저 화면에 렌더링하는 영역
    # -----------------------------------------------------

    # 1.
    # 화면 구성에 필요한 환경정보 설정
    #
    # 백엔드 엔드포인트 호출

    options = load_options()


    # -----------------------------------------------------
    # 라디오 버튼 초기값
    # -----------------------------------------------------

    # 백엔드가 알려준 기본값을 사용한다.

    st.session_state.setdefault(
        "tone",
        options["default_tone"],
    )


    st.session_state.setdefault(
        "length",
        options["default_length"],
    )


    # -----------------------------------------------------
    # 로그인 사용자 대화 목록 조회
    # -----------------------------------------------------

    # 세션의 토큰으로
    # 대화 목록 조회

    conversations = api(
        "GET",
        "/me/conversations",
        headers=auth_headers(),
    )


    # -----------------------------------------------------
    # 사이드바 렌더링
    # -----------------------------------------------------

    # 대화 목록으로
    # 사이드바 렌더링

    render_sidebar(
        options,
        conversations,
    )


    # 현재 면접관 옵션 표시

    st.caption(

        f"말투 {st.session_state.tone} "

        f"· 길이 {st.session_state.length}"
    )


    # -----------------------------------------------------
    # 사용자 상태별 화면
    # -----------------------------------------------------

    # -----------------------------------------------------
    # 상태 1
    # 로그인했지만 아직 대화가 하나도 없는 상태
    # -----------------------------------------------------

    if not conversations:


        render_empty(

            "아직 연습 기록이 없습니다.",

            "왼쪽에서 지원할 직무를 적고 "
            "`새 면접 연습 시작` 을 누르세요.",
        )


    # -----------------------------------------------------
    # 상태 2
    # 대화 목록은 있지만 선택된 대화가 없는 상태
    # -----------------------------------------------------

    # 방어 가지.
    #
    # selectbox가 첫 항목을 자동으로 고르므로
    # 평소에는 거의 닿지 않는다.
    #
    # 하지만 목록이 있는데
    # 선택값이 비어 있으면
    #
    # render_conversation(None)
    #
    # 이 되어 백엔드에서
    # 422가 날 수 있다.

    elif not st.session_state.conversation_id:


        render_empty(

            "연습할 면접을 고르세요.",

            "왼쪽 `지난 연습` 에서 "
            "하나를 선택하면 됩니다.",
        )


    # -----------------------------------------------------
    # 상태 3
    # 정상 대화
    # -----------------------------------------------------

    else:


        render_conversation(

            st.session_state.conversation_id,

            options[
                "max_history_messages"
            ],
        )


# =========================================================
# 화면 생성 영역
# =========================================================

st.title(
    SERVICE_NAME
)


# ---------------------------------------------------------
# 17일차 이전 코드
# ---------------------------------------------------------

# render_sidebar()
# 렌더 잊지말기


# st.caption(
#     "직무를 정하고 "
#     "면접 질문에 답하며 연습합니다."
# )


# st.caption(
#     f"말투 {st.session_state.tone} "
#     f"· 길이 {st.session_state.length}"
# )


# if not st.session_state.user_id:
#
#     render_empty(
#
#         "왼쪽에 user_id 를 입력하세요.",
#
#         "Supabase SQL Editor 에서 "
#         "`select id, username from profiles;` "
#         "로 확인할 수 있습니다.",
#     )


# elif not st.session_state.conversation_id:
#
#     render_empty(
#
#         "연습할 면접을 고르거나 새로 시작하세요.",
#
#         "왼쪽에서 직무를 적고 "
#         "`새 면접 시작` 을 누르면 됩니다.",
#     )


# else:
#
#     render_conversation(
#         st.session_state.conversation_id
#     )


# ---------------------------------------------------------
# 18일차 초기에 사용했던 로그인 분기
# ---------------------------------------------------------

# 로그인한 세션정보가 있을 때 확인


# if st.session_state.access_token:
#
#     conversations = api(
#         "GET",
#         "/me/conversations",
#         headers=auth_headers(),
#     )
#
#
#     render_sidebar(
#         options,
#         conversations,
#     )
#
#
#     st.write(
#         f"{st.session_state.user_email} "
#         "로 로그인했습니다."
#     )
#
#
# else:
#
#     render_login()


# =========================================================
# 최종 화면 생성 영역
# =========================================================

try:


    # -----------------------------------------------------
    # access_token 존재
    # -> 로그인된 사용자
    # -----------------------------------------------------

    if st.session_state.access_token:


        render_signed_in()


    # -----------------------------------------------------
    # access_token 없음
    # -> 로그인 화면
    # -----------------------------------------------------

    else:


        render_login()


# ---------------------------------------------------------
# 세션 만료
# ---------------------------------------------------------

except SessionExpired as error:


    # 토큰을 지우고
    # 로그인 화면으로 돌린다.
    #
    # 이유는 다음 실행에서
    # render_login()의 warning으로 보여준다.

    sign_out(
        str(error)
    )


# ---------------------------------------------------------
# 일반 API 오류
# ---------------------------------------------------------

except ApiError as error:


    st.error(
        str(error)
    )


# =========================================================
# 세션 정보 만료
# -> sign_out()
# =========================================================