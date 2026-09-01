import hashlib
import json

from fastapi import Depends, HTTPException
from app.db import get_anon_client
from app.schemas import CurrentUser
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.redis_client import r

#사용할 캐시 가져오기
from app.cache import cache_get, cache_set


# def get_current_user(authorization: str = Header(...)) -> CurrentUser:
#     if not authorization.startswith("Bearer "):
#         raise HTTPException(status_code=401, detail="Bearer 토큰이 필요합니다")

#     #실제 토큰 부분만 뗴기
#     token = authorization.removeprefix("Bearer ")

#     #서버에 보관중인 토큰 가져오기
#     client = get_anon_client()
#     try:
#         result = client.auth.get_user(token)
#     except Exception as e:
#         if "expired" in str(e).lower():
#             raise HTTPException(
#                 status_code=422,
#                 detail="토큰이 만료되었습니다"
#             )

#         raise HTTPException(
#             status_code=401,
#             detail="유효하지 않은 토큰입니다"
#         )

#     #유효 토큰 확인한 사용자 정보 반환
#     return CurrentUser(id=str(result.user.id), email=result.user.email, token=token)

## bearer 체크 
# bearer_scheme = HTTPBearer()

# def get_current_user(
#     credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
# ) -> CurrentUser:
#     # "Bearer " 접두어는 HTTPBearer 가 이미 떼어냈다.
#     # 헤더가 없거나 형식이 틀리면 여기 오기 전에 401 로 막힌다.
#     # 클라이언트가 보내 토큰
#     token = credentials.credentials

#     #수퍼베이스 서버에 보관중인 토큰과 비교해서 결과 가져옴
#     client = get_anon_client()
#     try:
#         result = client.auth.get_user(token)
#     except Exception as e:
#             if "expired" in str(e).lower():
#                 #요청 토큰이 서버에 저장된 토큰과 일치하지 않을 때
#                 raise HTTPException(
#                     status_code=422,
#                     detail="토큰이 만료되었습니다"
#                 )
    
#             raise HTTPException(
#                 status_code=401,
#                 detail="유효하지 않은 토큰입니다"
#             )

#     # 유효한 토큰 사용자 정보 반환
#     return CurrentUser(id=str(result.user.id), email=result.user.email, token=token)


bearer_scheme = HTTPBearer()
SESSION_CACHE_TTL_SECONDS = 300 

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> CurrentUser:
    # "Bearer " 접두어는 HTTPBearer 가 이미 떼어냈다.
    # 헤더가 없거나 형식이 틀리면 여기 오기 전에 401 로 막힌다.
    # 클라이언트가 보내 토큰 꺼내기
    token = credentials.credentials

    cache_key = f"session:{hashlib.sha256(token.encode()).hexdigest()}"

    #캐시에서 get

    # 캐시 직접 등록 x
    # cached = r.get(cache_key) 

    # 공통 캐시 오류 처리 가져오기 @@@@@@@@@@
    cached = cache_get(cache_key)

    #hit
    if cached:
        data = json.loads(cached) #캐시의 사용자 정보
        return CurrentUser(
                    id=data["id"], 
                    email=data["email"], 
                    token=token #서버에서 찾을거니까 원본 토큰 
                    )

    # miss일 때 서버에서 가져오기
    # 수퍼베이스 서버에 보관중인 토큰과 비교해서 결과 가져옴
    client = get_anon_client()
    try:
        result = client.auth.get_user(token)
    except Exception as e:
            if "expired" in str(e).lower():
                # 요청 토큰이 서버에 저장된 토큰과 일치하지 않을 때
                raise HTTPException(
                    status_code=422,
                    detail="토큰이 만료되었습니다"
                )
    
            raise HTTPException(
                status_code=401,
                detail="유효하지 않은 토큰입니다"
            )

    # 수퍼베이스에서 사용자 정보 가져오기
    current_user = CurrentUser(id=str(result.user.id), email=result.user.email, token=token)

    # 캐시에 set - 직접 등록
    # r.set(
    #     cache_key,
    #     json.dumps({"id": current_user.id, "email": current_user.email}),
    #     ex=SESSION_CACHE_TTL_SECONDS,
    # )

    # 공통 캐시 오류 처리 가져오기 @@@@@@@@@@
    cache_set(
        cache_key,
        json.dumps({"id": current_user.id, 
                    "email": current_user.email}),
        SESSION_CACHE_TTL_SECONDS,
    )

    # 유효한 토큰 사용자 정보 반환
    # return CurrentUser(id=str(result.user.id), email=result.user.email, token=token) -> 수퍼베이스가 보내준 모양
    return current_user

