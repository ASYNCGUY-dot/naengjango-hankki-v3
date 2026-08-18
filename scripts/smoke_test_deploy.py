"""배포된 서비스를 실제로 태워본다 (2026-08-18).

로컬 테스트가 덮지 못하는 것을 본다. 지금까지 브라우저 확인은 전부 "로컬 프론트 ->
로컬 백엔드"였는데, 배포는 "Render 정적 사이트 -> Render API"라 경계가 다르다. 특히
CORS는 그 경계에서만 진짜로 검증된다.

사용법:
    .venv/Scripts/python.exe scripts/smoke_test_deploy.py

계정을 새로 만들지 않는다. 기존 검증 계정으로 로그인만 한다 - 운영 DB에 쓰레기 계정을
늘리지 않기 위해서다(005의 삭제 목록에 이미 들어 있는 계정이다).
"""

import os
import sys
import time

import requests
from dotenv import load_dotenv

API = "https://naengjango-hankki-v2-api.onrender.com"
WEB = "https://naengjango-hankki-v3-web.onrender.com"
USER = "e2e_usage_20260818"
PW = "pw12345678"

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

failures: list[str] = []


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
paths = len(res.json()["paths"])
check("V3 코드인가 (경로 48개)", paths == 48, f"{paths}개")

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
res = requests.post(f"{API}/auth/login", json={"username": USER, "password": PW}, timeout=60)
if not check("로그인", res.status_code == 200, str(res.status_code)):
    print("\n로그인이 안 되면 나머지를 볼 수 없다. 중단한다.")
    print(res.text[:300])
    sys.exit(1)
data = res.json()
user_id, headers = data["user_id"], {"Authorization": f"Bearer {data['token']}"}

res = requests.get(f"{API}/profile/{user_id}", headers=headers, timeout=60)
check("내 정보", res.status_code == 200, str(res.status_code))

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
    cur.execute(
        "SELECT event, COUNT(*) FROM usage_events WHERE created_at > %s GROUP BY event ORDER BY event",
        (time.strftime("%Y-%m-%dT%H:", time.gmtime()),),
    )
    rows = cur.fetchall()
    check("이번 시간대 이벤트 기록", bool(rows), ", ".join(f"{e}={n}" for e, n in rows) or "없음")
    conn.close()
except Exception as exc:  # noqa: BLE001
    check("사용 로그 확인", False, f"{type(exc).__name__}: {exc}")

print()
if failures:
    print(f"실패 {len(failures)}건: {failures}")
    sys.exit(1)
print("전부 통과.")
