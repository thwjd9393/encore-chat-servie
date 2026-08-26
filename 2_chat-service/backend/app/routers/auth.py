from fastapi import APIRouter, HTTPException

from app.db import get_anon_client
from app.schemas import LoginRequest, SignupRequest, TokenResponse

auth_router = APIRouter(prefix="/auth", tags=["auth"])

@auth_router.post("/signup", response_model=TokenResponse)
def signup(req: SignupRequest):
    client = get_anon_client()
    try:
        ## 수파베이스 auth 테이블에 회원 저장
        result = client.auth.sign_up(  ## auth의 내장 함수
            {"email": req.email, "password": req.password}
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 성공하면 토큰생성
    access_token = result.session.access_token if result.session else None
    return TokenResponse(
        access_token=access_token,
        user_id=str(result.user.id),
        email=result.user.email,
    )

@auth_router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest):
    # 1. 클라이언트 생성
    client = get_anon_client()
    try:
        # 2. 수파베이스 auth 모듈의 비밀번호 로그인 호출
        result = client.auth.sign_in_with_password(
            {"email": req.email, "password": req.password}
        )
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))

    access_token = result.session.access_token if result.session else None
    return TokenResponse(
        access_token=access_token,
        user_id=str(result.user.id),
        email=result.user.email,
    )