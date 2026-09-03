from uuid import UUID

#내 정보 조회용 라우터
from fastapi import APIRouter, Depends, HTTPException

from app.db import get_anon_client
from app.deps import CurrentUser, get_current_user
from app.schemas import ConversationOut, ConversationUpdate, UpdateUser ,ProfileResponse, MyConversationCreate


me_router = APIRouter(prefix="/me", tags=["me"])

#Depends란? 의존성 주입, 특정 함수를 먼저 실행하고, 그 결과를 API함수에 전달하는 기능
# 디펜던시 - 외부 모듈 행하고 난 결과를 반환해주면 그걸 엔드포인트에 넣어줌

# Depends 안에서 아래 코드가 실행되고 있다
# client = get_anon_client()
# client.postgrest.auth(current_user.token)
# result = client.table("conversations").select("*").execute()

# get_anon_client -> 이 키로 접속하면 where 조건을 걸지않아도 개인의 데이터만 골라온다 
# RLS 가 DB 에서 막고 있기 때문

@me_router.get("")
def read_me(current_user: CurrentUser = Depends(get_current_user)):
    return {"id": current_user.id, "email": current_user.email}

# @me_router.get("/conversations", response_model=list[ConversationOut])
# def my_conversations(current_user: CurrentUser = Depends(get_current_user)):
#     client = get_anon_client() #토큰 비교
#     client.postgrest.auth(current_user.token)
#     result = (
#         client.table("conversations")
#         .select("*")
#         .order("created_at", desc=True)
#         .execute()
#     )
#     return result.data

@me_router.post("/conversations", response_model=ConversationOut)
def create_my_conversation(
    payload: MyConversationCreate,
    current_user: CurrentUser = Depends(get_current_user),
):
    client = get_anon_client()
    client.postgrest.auth(current_user.token)
    result = (
        client.table("conversations")
        .insert({"user_id": current_user.id, "title": payload.title})
        .execute()
    )
    return result.data[0]

@me_router.get("/profile", response_model=list[ProfileResponse])
def my_profile(current_user: CurrentUser = Depends(get_current_user)):
    client = get_anon_client() #토큰 비교
    client.postgrest.auth(current_user.token)
    result = (
        client.table("profiles")
        .select("*")
        .execute()
    )
    return result.data

@me_router.patch("/profile", response_model=list[ProfileResponse])
def my_profile(userUpdate:UpdateUser ,current_user: CurrentUser = Depends(get_current_user)):
    client = get_anon_client() #토큰 비교
    client.postgrest.auth(current_user.token)
    result = (
        client.table("profiles")
        .update({"username": userUpdate.username})
        .eq("id", str(current_user.id))
        .execute()
    )
    return result.data


@me_router.patch("/conversations/{conversation_id}", response_model=ConversationOut)
def rename_my_conversation(
    conversation_id: UUID,
    payload: ConversationUpdate,
    current_user: CurrentUser = Depends(get_current_user),
):
    client = get_anon_client()
    client.postgrest.auth(current_user.token)
    result = (
        client.table("conversations")
        .update({"title": payload.title})
        .eq("id", str(conversation_id))
        .execute()
    )
    if not result.data:
        # 없는 대화와 남의 대화를 구분하지 않고 똑같이 404 로 답한다.
        # 구분해서 알려주면 "그 대화는 존재한다"는 정보를 흘리게 된다.
        raise HTTPException(status_code=404, detail="conversation not found")
    return result.data[0]


@me_router.delete("/conversations/{conversation_id}", status_code=204)
def delete_my_conversation(
    conversation_id: UUID, current_user: CurrentUser = Depends(get_current_user)
):
    client = get_anon_client()
    client.postgrest.auth(current_user.token)
    result = (
        client.table("conversations").delete().eq("id", str(conversation_id)).execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="conversation not found")