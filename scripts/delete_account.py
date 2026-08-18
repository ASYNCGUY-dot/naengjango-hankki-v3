"""계정과 그에 딸린 개인정보를 전부 지운다 (2026-08-18).

왜 필요한가
개인정보 수집·이용 안내에 "요청하면 지워드립니다"라고 적으려면 실제로 지울 수단이
있어야 한다. 화면에는 탈퇴 기능이 없고(Phase 4 범위 밖), 지인 5명 규모에서는 연락받아
직접 처리하는 편이 낫다. 약속만 하고 수단이 없으면 그 문서는 거짓말이 된다.

무엇을 지우는가
users 행과, 그 사용자를 참조하는 모든 자식 행이다. 자식을 먼저 지워야 한다 -
001_schema.sql이 만든 참조에는 ON DELETE 규칙이 없어서 users를 바로 지우면 외래키
위반이 난다. 006/007이 만든 것(동의 이력·초기화 토큰·사용 로그)만 CASCADE로 따라온다.

사용자가 등록한 레시피(user_recipes)는 지우지 않는다. 승인돼서 다른 사람에게 보이고
있다면 그건 이미 서비스의 콘텐츠다. 대신 작성자 연결만 끊는다.

사용법:
    .venv/Scripts/python.exe scripts/delete_account.py <아이디>
    .venv/Scripts/python.exe scripts/delete_account.py <아이디> --yes   (확인 없이)

되돌릴 수 없다. 실행 전에 무엇이 지워지는지 보여주고 한 번 묻는다.
"""

import os
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

# 지우는 순서가 곧 외래키 의존 순서다. migration/005와 같게 유지할 것.
CHILD_TABLES = [
    ("ingredients", "user_id", "냉장고 재료"),
    ("reviews", "user_id", "후기"),
    ("favorites", "user_id", "즐겨찾기"),
    ("ingredient_favorites", "user_id", "재료 즐겨찾기"),
    ("recipe_likes", "user_id", "레시피 좋아요"),
    ("user_partner_keys", "user_id", "제휴 키"),
    ("auth_tokens", "user_id", "로그인 토큰"),
    ("user_consents", "user_id", "동의 이력"),
    ("password_reset_tokens", "user_id", "초기화 토큰"),
    ("usage_events", "user_id", "사용 기록"),
]


def main() -> int:
    args = [a for a in sys.argv[1:] if a != "--yes"]
    skip_confirm = "--yes" in sys.argv
    if len(args) != 1:
        print(__doc__)
        return 1
    username = args[0].strip()

    url = os.getenv("POSTGRES_URL")
    if not url:
        print("POSTGRES_URL이 비어 있습니다. .env를 확인하세요.")
        return 1

    conn = psycopg2.connect(url)
    cur = conn.cursor()

    cur.execute(
        "SELECT id, name, email, is_admin FROM public.users WHERE username = %s", (username,)
    )
    row = cur.fetchone()
    if row is None:
        print(f"'{username}' 계정이 없습니다.")
        conn.close()
        return 1

    user_id, name, email, is_admin = row
    if is_admin:
        print(f"'{username}'은 관리자 계정입니다. 이 스크립트로는 지우지 않습니다.")
        conn.close()
        return 1

    print(f"\n지울 계정: {username} ({name}, {email})")
    print("함께 지워지는 것:")
    total = 0
    for table, column, label in CHILD_TABLES:
        cur.execute(f"SELECT COUNT(*) FROM public.{table} WHERE {column} = %s", (user_id,))
        n = cur.fetchone()[0]
        if n:
            print(f"  {label:14} {n}행")
            total += n
    print(f"  {'계정 정보':14} 1행  (이름·연락처·이메일·성별·연령대·알레르기·병력 포함)")
    print(f"\n합계 {total + 1}행. 되돌릴 수 없습니다.")

    if not skip_confirm:
        answer = input("\n정말 지울까요? 계정 아이디를 그대로 입력하세요: ").strip()
        if answer != username:
            print("입력이 다릅니다. 중단합니다.")
            conn.close()
            return 1

    for table, column, _ in CHILD_TABLES:
        cur.execute(f"DELETE FROM public.{table} WHERE {column} = %s", (user_id,))
    # 등록한 레시피는 남기고 작성자 연결만 끊는다. 이미 서비스의 콘텐츠이기 때문이다.
    cur.execute(
        "UPDATE public.ingredient_submissions SET submitted_by = NULL WHERE submitted_by = %s",
        (user_id,),
    )
    cur.execute(
        "UPDATE public.ingredient_submissions SET reviewed_by = NULL WHERE reviewed_by = %s",
        (user_id,),
    )
    cur.execute("DELETE FROM public.users WHERE id = %s", (user_id,))
    conn.commit()
    conn.close()

    print(f"\n{username} 삭제 완료.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
