"""배포된 서비스를 실제로 태워본다 (2026-08-18).

로컬 테스트가 덮지 못하는 것을 본다. 지금까지 브라우저 확인은 전부 "로컬 프론트 ->
로컬 백엔드"였는데, 배포는 "Render 정적 사이트 -> Render API"라 경계가 다르다. 특히
CORS는 그 경계에서만 진짜로 검증된다.

사용법:
    .venv/Scripts/python.exe scripts/smoke_test_deploy.py

계정은 실행할 때마다 새로 만들고 끝나면 지운다. 처음에는 고정된 검증 계정을 썼는데,
migration/005가 그런 계정을 정리하는 순간 이 스크립트가 같이 죽는다. 언제 돌려도
결과가 같아야 하는 도구가 특정 계정의 생존에 기대면 안 된다.

지우는 대상은 이 스크립트가 방금 만든 계정 하나뿐이다. 이름이 정확히 일치할 때만 지운다.

자식 행을 먼저 지워야 한다. 001_schema.sql이 만든 참조에는 ON DELETE 규칙이 없어서
users를 바로 지우면 외래키 위반이 난다(2026-08-18에 실제로 났다). 006/007이 만든
테이블만 CASCADE라 알아서 따라온다. migration/005가 삭제 순서를 지키는 이유와 같다.
"""

import json
import os
import sys
import time
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

API = "https://naengjango-hankki-v2-api.onrender.com"
WEB = "https://naengjango-hankki-v3-web.onrender.com"

# 이 실행에서만 쓰는 계정. 같은 초에 두 번 돌리지 않는 한 겹치지 않는다.
USER = "smoke_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
PW = "pw12345678"

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

failures: list[str] = []


# users를 참조하면서 ON DELETE 규칙이 없는 테이블들. 먼저 비워야 계정을 지울 수 있다.
CHILD_TABLES = [
    ("ingredients", "user_id"),
    ("reviews", "user_id"),
    ("favorites", "user_id"),
    ("ingredient_favorites", "user_id"),
    ("recipe_likes", "user_id"),
    ("user_partner_keys", "user_id"),
    ("auth_tokens", "user_id"),
    ("ingredient_submissions", "submitted_by"),
    ("ingredient_submissions", "reviewed_by"),
]


def cleanup(username: str) -> None:
    """이 스크립트가 만든 계정을 지운다. 실패해도 검사 결과를 뒤집지 않는다."""
    try:
        import psycopg2

        conn = psycopg2.connect(os.environ["POSTGRES_URL"])
        cur = conn.cursor()
        # 이름이 정확히 일치할 때만. 조건이 넓어지면 남의 계정까지 지운다.
        cur.execute("SELECT id FROM public.users WHERE username = %s", (username,))
        row = cur.fetchone()
        if row is None:
            conn.close()
            print(f"\n정리: {username}이 이미 없습니다.")
            return

        for table, column in CHILD_TABLES:
            cur.execute(f"DELETE FROM public.{table} WHERE {column} = %s", (row[0],))
        cur.execute("DELETE FROM public.users WHERE id = %s", (row[0],))
        conn.commit()
        conn.close()
        print(f"\n정리: 검증 계정 {username} 삭제 완료")
    except Exception as exc:  # noqa: BLE001
        print(f"\n정리 실패({type(exc).__name__}). 계정 {username}이 남아 있으니 직접 지우세요.")


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"  {'OK  ' if ok else 'FAIL'} {label:44} {detail}")
    if not ok:
        failures.append(label)
    return ok


print("1) 서비스가 살아 있는가")
start = time.perf_counter()
res = requests.get(f"{WEB}/", timeout=60)
check("정적 사이트", res.status_code == 200, f"{res.status_code}  {time.perf_counter()-start:.2f}s")

start = time.perf_counter()
res = requests.get(f"{API}/openapi.json", timeout=180)
elapsed = time.perf_counter() - start
check("API", res.status_code == 200, f"{res.status_code}  {elapsed:.2f}s")
# 개수를 박아두면 엔드포인트를 하나 더할 때마다 이 스크립트가 거짓으로 운다(실제로 그랬다).
# 저장소의 명세와 대조하면 "배포가 지금 코드인가"를 직접 묻는 검사가 된다.
_repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(_repo, "frontend", "openapi.json"), encoding="utf-8") as f:
    expected_paths = set(json.load(f)["paths"])
missing = sorted(expected_paths - set(res.json()["paths"]))
check(
    "배포가 저장소와 같은 코드인가",
    not missing,
    f"경로 {len(res.json()['paths'])}개" + (f" / 빠진 것: {missing}" if missing else ""),
)

print("\n2) CORS - 이 경계는 배포에서만 검증된다")
res = requests.options(
    f"{API}/auth/login",
    headers={
        "Origin": WEB,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    },
    timeout=60,
)
allow_origin = res.headers.get("access-control-allow-origin", "")
check("preflight(OPTIONS) 응답", res.status_code in (200, 204), str(res.status_code))
check("allow-origin이 정적 사이트를 허용", allow_origin in (WEB, "*"), repr(allow_origin))

res = requests.get(f"{API}/recommendation/recipes/67", headers={"Origin": WEB}, timeout=60)
check(
    "실제 GET 응답에도 CORS 헤더",
    res.headers.get("access-control-allow-origin", "") in (WEB, "*"),
    repr(res.headers.get("access-control-allow-origin", "")),
)

print("\n3) 지인이 밟을 흐름 그대로")
res = requests.post(
    f"{API}/auth/signup",
    json={
        "username": USER, "password": PW, "name": "스모크", "phone": "010-0000-0000",
        "email": f"{USER}@example.com", "gender": "여성", "age_group": "20대",
        "consents": {"terms_of_service": True, "privacy": True, "marketing": False},
    },
    timeout=60,
)
if not check("회원가입", res.status_code == 200, str(res.status_code)):
    print("\n가입이 안 되면 나머지를 볼 수 없다. 중단한다.")
    print(res.text[:300])
    sys.exit(1)

res = requests.post(f"{API}/auth/login", json={"username": USER, "password": PW}, timeout=60)
if not check("로그인", res.status_code == 200, str(res.status_code)):
    print("\n로그인이 안 되면 나머지를 볼 수 없다. 중단한다.")
    print(res.text[:300])
    cleanup(USER)
    sys.exit(1)
data = res.json()
user_id, headers = data["user_id"], {"Authorization": f"Bearer {data['token']}"}

res = requests.get(f"{API}/profile/{user_id}", headers=headers, timeout=60)
check("내 정보", res.status_code == 200, str(res.status_code))

profile_body = {
    "gender": "여성", "age_group": "20대", "allergy": "달걀",
    "health_goal": "체중감량", "purpose": "자취생 식단관리", "cooking_level": "초급",
    "supplements": "없음", "household_size": 1, "novelty_pref": "새로운 메뉴 선호",
    "cooking_tools": "가스레인지", "medical_conditions": "",
}

# 동의 없이 보낸 건강 정보는 서버가 거절해야 한다. 이게 통과해버리면 동의 절차가
# 화면에만 있고 서버에는 없다는 뜻이다.
res = requests.put(
    f"{API}/profile/{user_id}", json=profile_body, headers=headers, timeout=60
)
check("동의 없는 알레르기는 거절된다", res.status_code == 422, str(res.status_code))

res = requests.put(
    f"{API}/profile/{user_id}",
    json={**profile_body, "health_data_consent": True},
    headers=headers,
    timeout=60,
)
check("온보딩 저장(동의 포함)", res.status_code == 200, str(res.status_code))

res = requests.get(f"{API}/profile/allergy-options", headers=headers, timeout=60)
check("알레르기 목록(V3 신규)", res.status_code == 200 and len(res.json()) > 0,
      f"{res.status_code}, {len(res.json()) if res.status_code == 200 else 0}개")

res = requests.post(f"{API}/pantry/{user_id}", json={"name": "두부"}, headers=headers, timeout=60)
check("재료 추가", res.status_code == 200, str(res.status_code))

res = requests.get(f"{API}/pantry/{user_id}", headers=headers, timeout=60)
check("냉장고 조회", res.status_code == 200, f"{res.status_code}, {len(res.json())}개")

start = time.perf_counter()
res = requests.get(
    f"{API}/recommendation/{user_id}", params={"ingredients": ["두부"]}, headers=headers, timeout=120
)
check("추천", res.status_code == 200 and len(res.json()) > 0,
      f"{res.status_code}, {len(res.json()) if res.status_code == 200 else 0}개, {time.perf_counter()-start:.2f}s")

res = requests.get(f"{API}/recommendation/recipes/67", timeout=60)
check("레시피 상세(비로그인 - 링크 공유)", res.status_code == 200 and res.json().get("ingredients"),
      f"{res.status_code}, 재료 {len(res.json().get('ingredients', []))}개")

res = requests.get(f"{API}/recommendation/recipes/categories", timeout=60)
check("분류 목록(V3 신규)", res.status_code == 200 and len(res.json()) > 0,
      f"{res.status_code}, {len(res.json()) if res.status_code == 200 else 0}개")

print("\n4) 사용 로그가 운영 DB에 쌓였는가")
try:
    import psycopg2

    conn = psycopg2.connect(os.environ["POSTGRES_URL"])
    cur = conn.cursor()
    # 이 실행이 남긴 것만 본다. 다른 사람 활동이 섞이면 검사가 아니라 구경이 된다.
    cur.execute(
        "SELECT event, COUNT(*) FROM usage_events WHERE user_id = %s GROUP BY event ORDER BY event",
        (user_id,),
    )
    rows = cur.fetchall()
    got = {event for event, _ in rows}
    expected = {"login", "onboarding_done", "pantry_add", "recommend"}
    check(
        "이번 실행의 이벤트 기록",
        expected <= got,
        ", ".join(f"{e}={n}" for e, n in rows) or "없음",
    )
    conn.close()
except Exception as exc:  # noqa: BLE001
    check("사용 로그 확인", False, f"{type(exc).__name__}: {exc}")

cleanup(USER)

print()
if failures:
    print(f"실패 {len(failures)}건: {failures}")
    sys.exit(1)
print("전부 통과.")
