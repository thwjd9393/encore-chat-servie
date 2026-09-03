"""면접관 응답을 만드는 라우터.

"""

import datetime
import json
import time
from uuid import UUID

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from google.genai import types

from app.db import supabase
from app.gemini_client import (
    DEFAULT_LENGTH,
    DEFAULT_TONE,
    GEMINI_MODEL,
    LENGTHS,
    TONES,
    build_system_prompt,
    client,
)

#메세지 생성할 떄 필요한 라우터 == create_message
#모델에게 보낼 이전 대화를 만들기 위한 import == list_messages
from app.routers.conversations import create_message, list_messages

from app.schemas import (
    ChatRequest,
    MessageCreate,
    MessageOut,
    FeedbackRequest,
    RegenerateRequest,
)

from app.redis_client import r


# 사용자와 면접관 메시지를 합쳐 최근 몇 개까지 모델에 보낼지.
# 20개면 대략 10번 주고받은 분량이다.
MAX_HISTORY_MESSAGES = 20

# 맥락을 끊는 표시. 실제 메시지처럼 저장하지만 모델에는 보내지 않는다.
# 새 컬럼을 만들지 않고 기존 role 을 쓰는 이유는, 화면에 그대로 보여줘야 하기 때문이다.
# 사용자는 "여기서 끊었다"는 사실을 볼 수 있어야 한다.
CONTEXT_RESET_MARKER = "[맥락 초기화] 이 지점 이전은 면접관이 기억하지 않습니다."

# 우리 DB 의 role 을 Gemini 의 role 로 바꾼다.
# assistant == model
_ROLE_MAP = {
    "user": "user",
    "assistant": "model",
}

# Redis에 최근 사용 로그를 몇 개까지 남길지
MAX_USAGE_LOGS = 50


# 채팅 처리 엔드포인트 라우터
router = APIRouter(prefix="/conversations", tags=["chat"])

#톤, 길이 등 설정하는 엔드포인트 라우터
options_router = APIRouter(prefix="/chat", tags=["chat"])


# ----------------------------------------------------------------
# 채팅 옵션
# ----------------------------------------------------------------

@options_router.get("/options")
def chat_options():
    """화면이 그릴 선택지를 내려준다.

    채팅 옵션은 gemini_client.py 의 표에서만 관리한다.
    화면에 목록을 직접 적어두면 두 곳 모두에서 관리해야 한다.
    한쪽에 톤을 추가하고 다른 쪽을 잊으면, 버튼은 있는데 아무 효과가 없다.
    """
    return {
        "tones": list(TONES),
        "lengths": list(LENGTHS),
        "default_tone": DEFAULT_TONE,
        "default_length": DEFAULT_LENGTH,

        # 화면이 "최근 20개를 기억합니다" 라고 알려줄 수 있게 함께 내려준다.
        "max_history_messages": MAX_HISTORY_MESSAGES,
    }


# ----------------------------------------------------------------
# 내부 함수
# ----------------------------------------------------------------

#내부함수
def _job_title(conversation_id: UUID) -> str:
    """대화 제목이 곧 지원 직무다. 16일차에 `새 면접 시작` 에서 받은 값이다."""

    result = (  # 수파베이스 다녀오는 곳
        supabase.table("conversations")
        .select("title")
        .eq("id", str(conversation_id))
        .execute()
    )

    if not result.data:
        raise HTTPException(
            status_code=404,
            detail="conversation not found",
        )

    return result.data[0]["title"] or "지원 직무 미지정"


def _build_history(conversation_id: UUID) -> list[dict]:
    """모델에게 보낼 이전 대화를 만든다."""

    # 시간 오름차순, Redis 캐시 적용됨
    messages = list_messages(conversation_id)

    #--------------------------------------------
    # 최근 초기화 기점부터 메세지를 꺼내기 위한 코드
    # role == system은 초기화 버튼을 누르면 생기는 시스템 메세지!!!
    # (ex. 이 뒤부터 허용하는 메세지입니다)

    # 뒤에서부터 system 메시지를 찾는다.
    for index in range(len(messages) - 1, -1, -1):

        if messages[index]["role"] == "system":

            #role이 system인 거 찾아서 이 다음부터 가져오기
            messages = messages[index + 1 :]

            break

    #--------------------------------------------

    # 대화목록을 가져오는데 role중 system은 빼고 넣어와
    usable = [
        m
        for m in messages
        if m["role"] in _ROLE_MAP
    ]

    # 가장 최근 메시지만 Gemini에게 전달
    recent = usable[-MAX_HISTORY_MESSAGES:]

    # 우리 DB 역할값을 Gemini 역할값으로 변환
    return [
        {
            "role": _ROLE_MAP[m["role"]],
            "parts": [
                {
                    "text": m["content"]
                }
            ],
        }
        for m in recent
    ]


# ----------------------------------------------------------------
# 로그와 피드백
# ----------------------------------------------------------------

def _usage_log_key(conversation_id: UUID) -> str:
    return f"usage_log:{conversation_id}"


def _feedback_key(conversation_id: UUID) -> str:
    return f"feedback:{conversation_id}"


def _log_usage(
    conversation_id: UUID,
    started_at: float,
    usage,
) -> None:
    """언제 요청했고 얼마나 걸렸는지 남긴다.

    Redis 리스트에 넣고 최근 N건만 남긴다. 새 테이블을 만들지 않는 이유는
    이것이 서비스 데이터가 아니라 운영 기록이기 때문이다. 지워져도 서비스는 돈다.
    """

    entry = {
        "requested_at": datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat(),

        "latency_ms": round(
            (time.monotonic() - started_at) * 1000
        ),

        "prompt_tokens": getattr(
            usage,
            "prompt_token_count",
            None,
        ),

        "response_tokens": getattr(
            usage,
            "candidates_token_count",
            None,
        ),

        "total_tokens": getattr(
            usage,
            "total_token_count",
            None,
        ),
    }

    key = _usage_log_key(conversation_id)

    r.lpush(
        key,
        json.dumps(entry),
    )

    r.ltrim(
        key,
        0,
        MAX_USAGE_LOGS - 1,
    )


@router.post("/{conversation_id}/feedback")
def save_feedback(
    conversation_id: UUID,
    payload: FeedbackRequest,
):
    """어떤 답변이 도움이 됐는지 기록한다.

    메시지 하나에 값 하나라서 리스트가 아니라 해시를 쓴다.
    같은 메시지에 다시 누르면 덮어써야 하기 때문이다.
    """

    key = _feedback_key(conversation_id)

    if payload.value is None:

        # 취소
        r.hdel(
            key,
            str(payload.message_id),
        )

    else:
        r.hset(
            key,
            str(payload.message_id),
            payload.value,
        )

    return {
        "message_id": str(payload.message_id),
        "value": payload.value,
    }


@router.get("/{conversation_id}/feedback")
def read_feedback(conversation_id: UUID):
    """화면이 버튼의 눌린 상태를 그릴 수 있게 전부 돌려준다."""

    return r.hgetall(
        _feedback_key(conversation_id)
    )


@router.get("/{conversation_id}/usage-logs")
def usage_logs(conversation_id: UUID):

    raw = r.lrange(
        _usage_log_key(conversation_id),
        0,
        MAX_USAGE_LOGS - 1,
    )

    return [
        json.loads(item)
        for item in raw
    ]


# ----------------------------------------------------------------
# 맥락 초기화
# ----------------------------------------------------------------

# 대화 목록에 system role 찍기위한 함수
@router.post(
    "/{conversation_id}/reset-context",
    response_model=MessageOut,
)
def reset_context(conversation_id: UUID):
    """맥락을 끊는다. 기록은 지우지 않는다.

    주의: 메시지를 삭제하지 않는다. 사용자가 연습한 내용은 그대로 남아야 한다.
        지워지는 것은 "모델이 참고하는 범위"뿐이다.

    인증을 요구하지 않는다. 같은 라우터의 /chat, /messages 와 맞춘 것이다.
    셋 다 21일차에 함께 막는다. 여기만 막으면 규칙이 뒤죽박죽이 된다.
    """

    return create_message(
        conversation_id,
        MessageCreate(
            role="system",
            content=CONTEXT_RESET_MARKER,
        ),
    )


# ----------------------------------------------------------------
# 응답 생성
# ----------------------------------------------------------------

#스트리밍으로 바꾸기 - 답이 만들어지는 대로 흘려보낸다.
def _stream_answer(
    conversation_id: UUID,
    contents: list,
    system_prompt: str,
):
    """모델의 응답을 조각으로 흘려보내고, 끝나면 통째로 저장한다."""

    def event_stream():

        started_at = time.monotonic()

        # Gemini가 보내준 조각을 전부 합쳐서
        # 마지막에 DB에 하나의 메시지로 저장하기 위한 변수
        full_text = ""

        # 마지막 chunk에 들어오는 사용량 정보를 저장
        last_usage = None

        try:

            # 사용자메세지 + 제미나이 호출
            for chunk in client.models.generate_content_stream(
                model=GEMINI_MODEL,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt
                ),
            ):

                if chunk.text:

                    # 전체 답변 저장
                    full_text += chunk.text

                    # 주의: 조각 안의 줄바꿈은 그대로 보내면 SSE 형식이 깨진다.
                    #      한 이벤트는 빈 줄로 끝나기로 약속돼 있기 때문이다.
                    yield (
                        "data: "
                        + json.dumps(
                            {
                                "text": chunk.text
                            }
                        )
                        + "\n\n"
                    )

                if chunk.usage_metadata:

                    last_usage = chunk.usage_metadata


            # Gemini가 정상적으로 끝났지만
            # 실제 답변 내용이 없는 경우
            if not full_text:

                yield (
                    "data: "
                    + json.dumps(
                        {
                            "error": "모델이 빈 응답을 돌려주었습니다."
                        }
                    )
                    + "\n\n"
                )

                return


            # 다 받은 뒤에 한 번만 저장한다.
            # 조각마다 저장하면 메시지가 수십 개로 쪼개진다.
            saved = create_message(
                conversation_id,
                MessageCreate(
                    role="assistant",
                    content=full_text,
                ),
            )


            # Gemini 사용량과 응답시간 Redis 저장
            _log_usage(
                conversation_id,
                started_at,
                last_usage,
            )


            # -----------------------------------------------
            # 중요
            #
            # saved["id"]가 UUID 객체라면
            # json.dumps()에서 직렬화 오류가 발생할 수 있다.
            #
            # 그래서 str()로 변환한다.
            # -----------------------------------------------

            yield (
                "data: "
                + json.dumps(
                    {
                        "done": True,
                        "message_id": str(saved["id"]),
                    }
                )
                + "\n\n"
            )


        except Exception as e:

            # 스트림이 이미 시작돼 상태 코드를 바꿀 수 없다.
            # 이벤트로 알린다.
            #
            # Gemini 호출뿐 아니라
            # DB 저장 / Redis 저장 / JSON 변환 과정에서
            # 오류가 발생해도 SSE error 이벤트로 보내준다.
            yield (
                "data: "
                + json.dumps(
                    {
                        "error": f"{type(e).__name__}: {e}"
                    }
                )
                + "\n\n"
            )

            return


    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
    )


######################################################################
# 다시 생성
######################################################################

@router.post("/{conversation_id}/regenerate")
def regenerate(
    conversation_id: UUID,
    payload: RegenerateRequest,
):
    """마지막 답변을 지우고 다시 만든다.

    Retry 와 다르다. Retry 는 실패한 요청을 그대로 다시 보내는 것이고,
    Regenerate 는 **성공한 답변이 마음에 안 들 때** 새로 받는 것이다.
    그래서 여기서는 마지막 assistant 메시지를 지우는 일이 먼저다.
    """

    messages = list_messages(conversation_id)

    if (
        not messages
        or messages[-1]["role"] != "assistant"
    ):
        raise HTTPException(
            status_code=400,
            detail="다시 생성할 답변이 없습니다.",
        )


    supabase.table("messages") \
        .delete() \
        .eq("id", messages[-1]["id"]) \
        .execute()


    # 캐시를 지워야 방금 삭제가 반영된다
    r.delete(
        f"messages:{conversation_id}"
    )


    job_title = _job_title(conversation_id)


    # 삭제 후라 마지막 사용자 질문까지만 들어온다
    history = _build_history(conversation_id)


    if not history:
        raise HTTPException(
            status_code=400,
            detail="다시 생성할 질문이 없습니다.",
        )


    return _stream_answer(
        conversation_id,
        history,
        build_system_prompt(
            job_title,
            payload.tone,
            payload.length,
        ),
    )


######################################################################
###스트리밍 답변으로 변경#####################
######################################################################

@router.post("/{conversation_id}/chat")
def chat(
    conversation_id: UUID,
    payload: ChatRequest,
):

    # 대화방 제목 = 지원 직무
    job_title = _job_title(conversation_id)


    # 스트리밍을 시작하기 전에 끝내둔다.
    # 제너레이터 안에 두면
    # 클라이언트가 스트림을 끝까지 안 받았을 때 저장이 안 될 수 있다.
    history = _build_history(conversation_id)


    # 사용자 메시지를 DB에 먼저 저장
    create_message(
        conversation_id,
        MessageCreate(
            role="user",
            content=payload.content,
        ),
    )


    # 기존 대화 + 지금 사용자가 보낸 메시지
    contents = history + [
        {
            "role": "user",
            "parts": [
                {
                    "text": payload.content
                }
            ],
        }
    ]


    # SSE 스트리밍 응답 반환
    return _stream_answer(
        conversation_id,
        contents,

        #제미나이 시스팀 프롬포트
        build_system_prompt(
            job_title,
            payload.tone,
            payload.length,
        ),
    )


######################################################################
###스트리밍 답변 전#####################
######################################################################

# @router.post("/{conversation_id}/chat", response_model=MessageOut)
# def chat(conversation_id: UUID, payload: ChatRequest):
#     job_title = _job_title(conversation_id)
#     history = _build_history(conversation_id)

#     # 1) 사용자 메시지를 먼저 저장한다.
#     #    모델 호출이 실패해도(429 등) 사용자가 쓴 답변은 남아야 한다.
#     create_message(
#         conversation_id,
#         MessageCreate(
#             role="user",
#             content=payload.content
#         )
#     )

#     # 2) 제미나이 시스템 프롬프트를 생성한다.
#     system_prompt = build_system_prompt(
#         job_title,
#         payload.tone,
#         payload.length
#     )

#     # 3) 제미나이 프롬포트 생성

#     ###################################################
#     #### 질문 하나만 보냄################################

#     # try:
#     #     response = client.models.generate_content(
#     #         model=GEMINI_MODEL,
#     #         contents=payload.content,
#     #         config=types.GenerateContentConfig(
#     #             system_instruction=system_prompt
#     #         ),
#     #     )
#     # except Exception as e:
#     #     # 감싸지 않으면 FastAPI 가 원인 없는 500 만 돌려준다.
#     #     # 화면이 무엇 때문에 실패했는지 알 수 있어야 사용자에게 설명할 수 있다.
#     #     raise HTTPException(
#     #         #제미나이 에러 메세지 설정
#     #         status_code=503,
#     #         detail=f"응답 생성 실패: {type(e).__name__}: {e}"
#     #     )

#     ###################################################

#     # 기존 메세지까지 보내기 위한 contents
#     contents = history + [
#         {
#             "role": "user",
#             "parts": [
#                 {
#                     "text": payload.content
#                 }
#             ],
#         }
#     ]

#     try:
#         response = client.models.generate_content(
#             model=GEMINI_MODEL,
#             contents=contents,
#             config=types.GenerateContentConfig(
#                 system_instruction=system_prompt
#             ),
#         )

#     except Exception as e:

#         # 감싸지 않으면 FastAPI 가 원인 없는 500 만 돌려준다.
#         # 화면이 무엇 때문에 실패했는지 알 수 있어야 사용자에게 설명할 수 있다.
#         raise HTTPException(

#             #제미나이 에러 메세지 설정
#             status_code=503,
#             detail=f"응답 생성 실패: {type(e).__name__}: {e}"
#         )


#     # 주의: 안전 필터에 걸리면 예외가 아니라 text 가 None 으로 온다.
#     if not response.text:

#         raise HTTPException(

#             #제미나이 에러 메세지 설정
#             status_code=503,
#             detail=(
#                 "AI 모델이 빈 응답을 돌려주었습니다. "
#                 "질문을 바꿔서 다시 시도하세요."
#             )
#         )


#     return create_message(

#         #제미나이 응답을 assistant 메세지로 추가
#         conversation_id,
#         MessageCreate(
#             role="assistant",
#             content=response.text
#         )
#     )