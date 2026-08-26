from fastapi import Depends, HTTPException
from app.db import get_anon_client
from app.schemas import CurrentUser
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


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

bearer_scheme = HTTPBearer()

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> CurrentUser:
    # "Bearer " 접두어는 HTTPBearer 가 이미 떼어냈다.
    # 헤더가 없거나 형식이 틀리면 여기 오기 전에 401 로 막힌다.
    token = credentials.credentials

    client = get_anon_client()
    try:
        result = client.auth.get_user(token)
    except Exception as e:
            if "expired" in str(e).lower():
                raise HTTPException(
                    status_code=422,
                    detail="토큰이 만료되었습니다"
                )
    
            raise HTTPException(
                status_code=401,
                detail="유효하지 않은 토큰입니다"
            )

    return CurrentUser(id=str(result.user.id), email=result.user.email, token=token)


