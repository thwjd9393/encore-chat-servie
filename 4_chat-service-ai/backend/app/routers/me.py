#내 정보 조회용 라우터
from fastapi import APIRouter, Depends

from app.db import get_anon_client
from app.deps import CurrentUser, get_current_user
from app.schemas import ConversationOut, UpdateUser ,ProfileResponse


me_router = APIRouter(prefix="/me", tags=["me"])

#Depends란? 의존성 주입, 특정 함수를 먼저 실행하고, 그 결과를 API함수에 전달하는 기능
# 디펜던시 - 외부 모듈 행하고 난 결과를 반환해주면 그걸 엔드포인트에 넣어줌
@me_router.get("")
def read_me(current_user: CurrentUser = Depends(get_current_user)):
    return {"id": current_user.id, "email": current_user.email}

@me_router.get("/conversations", response_model=list[ConversationOut])
def my_conversations(current_user: CurrentUser = Depends(get_current_user)):
    client = get_anon_client() #토큰 비교
    client.postgrest.auth(current_user.token)
    result = (
        client.table("conversations")
        .select("*")
        .order("created_at", desc=True)
        .execute()
    )
    return result.data

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