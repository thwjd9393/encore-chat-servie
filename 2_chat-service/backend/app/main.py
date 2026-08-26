"""FastAPI 앱 진입점.

실행:  uv run uvicorn app.main:app --reload
확인:  http://127.0.0.1:8000/health  ·  http://127.0.0.1:8000/docs
"""

from fastapi import FastAPI
from app.routers import auth, conversations, me

app = FastAPI(title="chat-service", version="0.1.0")


app.include_router(auth.auth_router)
app.include_router(me.me_router)
app.include_router(conversations.conversation_router)


@app.get("/health")
def health():
    return {"status": "ok"}
