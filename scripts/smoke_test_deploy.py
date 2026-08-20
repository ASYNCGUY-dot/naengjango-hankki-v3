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

import base64
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

        # 이 계정이 등록한 레시피가 남아 있으면 users를 못 지운다. 정상 흐름에서는
        # DELETE /my-recipes/{id}로 이미 지워졌지만, 중간에 실패하면 남는다.
        cur.execute("SELECT id FROM public.recipes WHERE submitted_by = %s", (row[0],))
        for (recipe_id,) in cur.fetchall():
            for table in ("recipe_tags", "recipe_ingredients", "recipe_likes", "favorites"):
                cur.execute(f"DELETE FROM public.{table} WHERE recipe_id = %s", (recipe_id,))
            cur.execute("DELETE FROM public.recipes WHERE id = %s", (recipe_id,))

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
# is_admin은 마이 화면이 승인 대기 목록 링크를 보일지 정하는 데 쓴다. 경로 목록만
# 대조하는 위의 검사로는 필드 추가를 못 잡아서, 새 코드가 올라갔는지 여기서 확인한다.
check(
    "프로필이 is_admin을 준다",
    res.status_code == 200 and res.json().get("is_admin") is False,
    repr(res.json().get("is_admin")) if res.status_code == 200 else "-",
)

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

# 화면의 선택지가 전부 서버에서 온 것인지 본다. 화면이 목록을 따로 들고 있으면
# 사용자가 고른 값이 조용히 무시된다(V3_HANDOFF 8.-5).
res = requests.get(f"{API}/profile/options", timeout=60)
options = res.json() if res.status_code == 200 else {}
check(
    "가입 선택지(성별·연령대·병력)",
    res.status_code == 200
    and all(options.get(key) for key in ("genders", "age_groups", "medical_conditions")),
    f"{res.status_code}, 연령대 {len(options.get('age_groups', []))}개",
)

res = requests.post(f"{API}/pantry/{user_id}", json={"name": "두부"}, headers=headers, timeout=60)
check("재료 추가", res.status_code == 200, str(res.status_code))

res = requests.get(f"{API}/pantry/suggest", params={"keyword": "두"}, timeout=60)
check("재료 자동완성", res.status_code == 200 and len(res.json()) > 0,
      f"{res.status_code}, {len(res.json()) if res.status_code == 200 else 0}개")

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

res = requests.get(f"{API}/recommendation/recipes/themes", timeout=120)
themes = res.json() if res.status_code == 200 else []
check(
    "홈 테마",
    res.status_code == 200 and all(t.get("recipes") for t in themes),
    f"{res.status_code}, " + ", ".join(f"{t['title']} {len(t['recipes'])}개" for t in themes),
)

res = requests.get(
    f"{API}/recommendation/recipes/67/nutrition-fit",
    params={"user_id": user_id}, headers=headers, timeout=60,
)
fit = res.json() if res.status_code == 200 else {}
check(
    "영양 적합도",
    res.status_code == 200 and fit.get("available") and bool(fit.get("rows")),
    f"{res.status_code}, {fit.get('bracket_label')}, {len(fit.get('rows', []))}행",
)

res = requests.get(
    f"{API}/recommendation/recipes/67/substitution",
    params={"user_id": user_id}, headers=headers, timeout=60,
)
check(
    "부족한 재료·대체안",
    res.status_code == 200 and "missing_ingredients" in res.json(),
    f"{res.status_code}, 부족 {len(res.json().get('missing_ingredients', []))}개",
)

res = requests.post(f"{API}/favorites/{user_id}/67/toggle", headers=headers, timeout=60)
saved = res.status_code == 200 and res.json().get("favorited") is True
res = requests.get(f"{API}/favorites/{user_id}", headers=headers, timeout=60)
check(
    "즐겨찾기",
    saved and res.status_code == 200 and any(r["id"] == 67 for r in res.json()),
    f"토글 {saved}, 목록 {res.status_code}",
)

# ---------- 추천하기 (즐겨찾기와 다른 기능이다) ----------
# 공개 레시피라 다른 사람의 추천이 이미 있을 수 있다. 절대값이 아니라 증감을 본다.
# 확인이 끝나면 다시 눌러 되돌린다 - 검증 흔적이 홈의 인기 목록에 남으면 안 된다.
before = requests.get(
    f"{API}/recommendation/recipes/67/like", params={"user_id": user_id}, headers=headers, timeout=60
)
base_count = before.json().get("like_count") if before.status_code == 200 else None

on = requests.post(
    f"{API}/recommendation/recipes/67/like/toggle",
    params={"user_id": user_id}, headers=headers, timeout=60,
)
turned_on = on.status_code == 200 and on.json().get("liked") is True
counted = base_count is not None and on.json().get("like_count") == base_count + 1

popular = requests.get(f"{API}/recommendation/recipes/popular", timeout=60)
in_popular = popular.status_code == 200 and any(r["id"] == 67 for r in popular.json())
# 홈의 "많이 추천한 메뉴" 줄이 카드를 그리려면 사진이 필요하다.
has_image_field = popular.status_code == 200 and all("image_url" in r for r in popular.json())

off = requests.post(
    f"{API}/recommendation/recipes/67/like/toggle",
    params={"user_id": user_id}, headers=headers, timeout=60,
)
restored = off.status_code == 200 and off.json().get("like_count") == base_count

check(
    "추천하기(누르고 되돌리기)",
    turned_on and counted and restored,
    f"{base_count} -> {on.json().get('like_count')} -> {off.json().get('like_count')}",
)
check("인기 목록에 반영", in_popular and has_image_field,
      f"목록 {len(popular.json()) if popular.status_code == 200 else 0}개, 사진 필드 {has_image_field}")

# ---------- 후기 ----------
res = requests.post(
    f"{API}/reviews/67",
    json={"user_id": user_id, "rating": 5, "review_text": "배포 점검용 후기입니다."},
    headers=headers, timeout=60,
)
wrote = res.status_code == 200
# 목록은 로그인 없이도 읽혀야 한다. 상세가 링크로 공유되는 공개 화면이기 때문이다.
res = requests.get(f"{API}/reviews/67", timeout=60)
check(
    "후기 작성(비로그인 열람)",
    wrote and res.status_code == 200 and any(r["review_text"].startswith("배포 점검용") for r in res.json()),
    f"작성 {wrote}, 목록 {res.status_code}",
)

# ---------- 내 레시피 ----------
res = requests.post(
    f"{API}/my-recipes",
    params={"user_id": user_id},
    json={
        "menu_name": f"배포점검메뉴_{USER}", "category": "반찬", "calorie": 200.0,
        "ingredients_text": "계란 2개\n두부 100g", "steps_text": "썬다\n볶는다",
    },
    headers=headers, timeout=60,
)
submitted = res.status_code == 200
my_recipe_id = res.json().get("recipe_id") if submitted else None
# 새 이름이므로 승인 대기가 아니라 바로 공개여야 한다.
check("내 레시피 등록", submitted and res.json().get("status") == "approved",
      f"{res.status_code}, status={res.json().get('status') if submitted else '-'}")

res = requests.get(f"{API}/my-recipes", params={"user_id": user_id}, headers=headers, timeout=60)
listed = res.json() if res.status_code == 200 else []
check(
    "내 레시피 목록(상태·추천 수)",
    res.status_code == 200 and any(
        r["id"] == my_recipe_id and r["status"] == "approved" and r["like_count"] == 0 for r in listed
    ),
    f"{res.status_code}, {len(listed)}개",
)

# 등록한 레시피가 알레르기 태그를 못 받으면 그 레시피만 필터를 그냥 통과한다.
if my_recipe_id is not None:
    try:
        import psycopg2

        conn = psycopg2.connect(os.environ["POSTGRES_URL"])
        cur = conn.cursor()
        cur.execute(
            "SELECT tag_value FROM recipe_tags WHERE recipe_id = %s AND tag_type = 'allergy'",
            (my_recipe_id,),
        )
        tags = {row[0] for row in cur.fetchall()}
        conn.close()
        # "계란"은 이름이 그대로 있으니 원래도 잡혔다. "대두"는 재료가 "두부"뿐이라
        # 파생 재료 사전이 실제로 배포에 반영됐을 때만 잡힌다(2026-08-19).
        check(
            "등록 레시피에 알레르기 태그(파생 포함)",
            {"계란", "대두"} <= tags,
            ", ".join(sorted(tags)) or "없음",
        )
    except Exception as exc:  # noqa: BLE001
        check("등록 레시피에 알레르기 태그", False, f"{type(exc).__name__}: {exc}")

    res = requests.delete(
        f"{API}/my-recipes/{my_recipe_id}", params={"user_id": user_id}, headers=headers, timeout=60
    )
    check("내 레시피 삭제", res.status_code == 200, str(res.status_code))

# ---------- 자랑하기 ----------
# 사진 업로드는 배포된 서버에 SUPABASE_URL/SUPABASE_SERVICE_KEY가 들어가 있어야 된다.
# 이 두 개는 Render 대시보드에서만 넣을 수 있어서, 로컬 테스트로는 절대 안 걸린다.
JPEG_1X1 = base64.b64decode(
    "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0a"
    "HBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/wAALCAABAAEBAREA/8QAFAABAAAAAAAA"
    "AAAAAAAAAAAACf/EABQQAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAD8AKp//2Q=="
)
res = requests.post(
    f"{API}/brags/photo",
    params={"user_id": user_id},
    files={"file": ("check.jpg", JPEG_1X1, "image/jpeg")},
    headers=headers, timeout=120,
)
photo_url = res.json().get("image_url") if res.status_code == 200 else None
check(
    "자랑 사진 업로드",
    res.status_code == 200 and bool(photo_url),
    str(res.status_code) + (" (Render에 SUPABASE_* 환경변수가 없다)" if res.status_code == 503 else ""),
)
if photo_url:
    # 화면의 <img>가 하는 것과 같은 요청. 인증 없이 보여야 한다.
    check("사진이 로그인 없이 보인다", requests.get(photo_url, timeout=60).status_code == 200,
          photo_url.rsplit("/", 1)[-1])

res = requests.post(
    f"{API}/brags",
    params={"user_id": user_id},
    json={"recipe_id": 67, "body": f"배포 점검용 글 {USER}", "image_url": photo_url},
    headers=headers, timeout=60,
)
brag_id = res.json().get("id") if res.status_code == 200 else None
check("자랑 글 작성", res.status_code == 200 and bool(brag_id), str(res.status_code))

# 피드는 로그인 없이 읽혀야 한다 - 남의 음식 사진이 가장 강한 가입 유인이다.
res = requests.get(f"{API}/brags", timeout=60)
check(
    "자랑 피드(비로그인 열람)",
    res.status_code == 200 and any(b["id"] == brag_id for b in res.json()),
    f"{res.status_code}, {len(res.json()) if res.status_code == 200 else 0}개",
)

if brag_id:
    # 좋아요가 레시피 추천에도 반영되는지. 확인 후 되돌린다.
    before = requests.get(
        f"{API}/recommendation/recipes/67/like", params={"user_id": user_id}, headers=headers, timeout=60
    ).json().get("like_count")
    requests.post(
        f"{API}/brags/{brag_id}/like/toggle", params={"user_id": user_id}, headers=headers, timeout=60
    )
    after = requests.get(
        f"{API}/recommendation/recipes/67/like", params={"user_id": user_id}, headers=headers, timeout=60
    ).json().get("like_count")
    check("자랑 좋아요가 레시피 추천에 반영", after == before + 1, f"{before} -> {after}")

    requests.delete(f"{API}/brags/{brag_id}", params={"user_id": user_id}, headers=headers, timeout=60)
    res = requests.get(f"{API}/brags", timeout=60)
    check("자랑 글 삭제", all(b["id"] != brag_id for b in res.json()), str(res.status_code))

# 올린 사진은 API로 지울 수 없으므로 저장소에서 직접 지운다. 검증 흔적을 남기지 않는다.
if photo_url and os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SERVICE_KEY"):
    base = os.environ["SUPABASE_URL"].rstrip("/")
    key = os.environ["SUPABASE_SERVICE_KEY"]
    path = photo_url.split("/object/public/brag-photos/", 1)[-1]
    res = requests.delete(
        f"{base}/storage/v1/object/brag-photos/{path}",
        headers={"apikey": key, "Authorization": f"Bearer {key}"}, timeout=60,
    )
    check("올린 사진 정리", res.status_code == 200, str(res.status_code))

# ---------- 재료 정보 등록 ----------
res = requests.post(
    f"{API}/ingredient-submissions",
    params={"user_id": user_id},
    json={"ingredient_name": f"배포점검재료_{USER}", "calorie": 120.0},
    headers=headers, timeout=60,
)
check("재료 정보 등록", res.status_code == 200 and res.json().get("status") == "approved",
      f"{res.status_code}, status={res.json().get('status') if res.status_code == 200 else '-'}")

res = requests.post(
    f"{API}/ingredient-submissions",
    params={"user_id": user_id},
    json={"ingredient_name": "두부", "calorie": 1.0},
    headers=headers, timeout=60,
)
check("공식 DB에 있는 재료는 승인 대기", res.status_code == 200 and res.json().get("status") == "pending",
      f"{res.status_code}, status={res.json().get('status') if res.status_code == 200 else '-'}")

# ---------- 관리자 큐는 일반 계정에게 닫혀 있어야 한다 ----------
res = requests.get(f"{API}/admin/pending-recipes", params={"user_id": user_id}, headers=headers, timeout=60)
check("일반 계정은 승인 대기 목록을 못 본다", res.status_code == 403, str(res.status_code))

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
