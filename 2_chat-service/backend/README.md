# backend — 교육생 작업 폴더 (12 → 13 → 15일차)

**이 폴더 하나를 세 일차에 걸쳐 키운다.** 일차마다 새 폴더를 받는 것이 아니다.

지금 커밋되어 있는 것은 **12일차 시작 상태**다. `app/db.py`만 완성돼 있고 나머지는 `# TODO`다.

| 일차 | 여기서 하는 일 |
| --- | --- |
| **12** | `schemas.py`·`routers/users.py`·`routers/conversations.py`의 TODO를 채운다 |
| 13 | `routers/users.py`를 **삭제**하고 `auth.py`·`me.py`·`deps.py`를 더한다 |
| 15 | `redis_client.py`를 더하고 기존 파일에 캐싱을 얹는다 |

배포용 문서는 강사가 공유한 배포 문서 저장소(`2026-aio2-guide`)에 있다. 목록은 상위 폴더 `README.md` 참고.

## 현재 상태 (12일차 시작)

```
backend/
├── .env.example
├── pyproject.toml
└── app/
    ├── db.py                 완성. 실습 2에서 내용만 확인한다
    ├── main.py               /health 만. 라우터 등록이 TODO 2개
    ├── schemas.py            TODO 7개 (실습 3)
    └── routers/
        ├── users.py          TODO 6개 (실습 4·5)
        └── conversations.py  TODO 5개 (실습 6·7)
```

각 실습에서 해당 `# TODO`를 지우고 결과 코드를 채워 넣는다. TODO에는 실습 번호와 틀리기 쉬운 지점이 함께 적혀 있다.

## 실행

```powershell
cd 3_chat-service\backend
copy .env.example .env          # SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY 채우기
uv sync
uv run uvicorn app.main:app --reload
```

`http://127.0.0.1:8000/docs`에서 Swagger UI로 확인한다.
지금은 `GET /health` 하나만 보인다. 실습을 진행하며 늘어난다.

## 12일차 사전 조건

11일차 테이블과 데이터가 Supabase에 있어야 한다. 아래가 `4 / 4 / 9`로 나오면 준비 완료다.

```sql
select
    (select count(*) from users)         as 사용자수,
    (select count(*) from conversations) as 대화수,
    (select count(*) from messages)      as 메시지수;
```

> **주의:** 11일차 테이블을 지우지 않은 상태로 시작한다. 정리는 12일차 마지막에 한다
> (13일차의 `conversations`는 `users`가 아니라 `profiles`를 가리키므로 이름이 겹치면 안 된다).

## 12일차를 마치면 동작하는 것

| 메서드 | 주소 | 하는 일 | 성공 코드 |
| --- | --- | --- | --- |
| `GET` | `/health` | 서버 상태 확인 | 200 |
| `POST` | `/users` | 사용자 등록 | 201 |
| `GET` | `/users` | 사용자 목록(최신순) | 200 |
| `GET` | `/users/{user_id}` | 사용자 한 명 조회 | 200 |
| `PATCH` | `/users/{user_id}` | `username` 수정 | 200 |
| `DELETE` | `/users/{user_id}` | 사용자 삭제 | 204 |
| `POST` | `/conversations` | 대화 생성 | 201 |
| `GET` | `/conversations?user_id=` | 사용자별 대화 목록 | 200 |
| `POST` | `/conversations/{id}/messages` | 메시지 저장 | 201 |
| `GET` | `/conversations/{id}/messages` | 메시지 목록(시간순) | 200 |

## 막혔을 때

정답 코드는 `../instructor/day12_users`에 있다. 포트를 8001로 띄우면 지금 만든 것과 나란히 비교할 수 있다.

중간 일차부터 합류해야 한다면 `../README.md`의 "중간 일차부터 합류하려면"을 본다.

## 주의

- `pydantic[email]`이 없으면 `EmailStr` 때문에 서버가 시작되지 않는다. `pyproject.toml`에 넣어뒀다.
- `.env`는 커밋하지 않는다.
- `app` 폴더를 파이썬 패키지로 인식시키는 빈 `__init__.py`가 필요하다. 이미 있다.
