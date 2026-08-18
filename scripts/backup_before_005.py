"""migration/005가 지울 데이터를 미리 SQL 파일로 떠둔다 (2026-08-18).

왜 필요한가
005는 계정과 딸린 데이터를 지우고 되돌릴 수 없다. 원래는 Supabase 대시보드의 백업을
받아두라고 적어뒀는데, **무료 플랜에는 백업 기능이 없다**(대시보드에 "Free Plan does
not include project backups"라고 나온다). 로컬에 pg_dump도 없다. 그래서 005가 실제로
건드리는 범위만 골라서 직접 뜬다.

전체 덤프가 아니라 "005가 지울 것"만 뜨는 이유는, recipes와 ingredient_catalog가
수만 행이라 전체를 뜨면 크고 느린데 005는 그 테이블을 건드리지도 않기 때문이다.

무엇을 뜨는가
005의 doomed_users 조건을 그대로 다시 계산해서, 그 계정들의 users 행과 그들을
참조하는 모든 자식 행을 INSERT 문으로 쓴다. 되돌리려면 나온 .sql을 그대로 실행하면
된다(단, 005가 건 NOT NULL·UNIQUE 제약과 충돌하는 행은 그때 걸린다 - 그런 행이 바로
005가 지우려던 대상이다).

사용법:
    .venv/Scripts/python.exe scripts/backup_before_005.py
"""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

# 005의 doomed_users와 같은 조건. 여기가 어긋나면 백업이 실제 삭제 범위를 못 덮는다.
DOOMED_USERNAMES = (
    "testuser01", "test", "gaptest0718", "design_verify_20260726",
    "verify_ui_v2_20260721", "prod_verify_20260721", "design2_verify_local",
    "최지목", "e2e_verify_20260813", "e2e_usage_20260818",
)

# (테이블, 사용자를 가리키는 컬럼) - 005가 지우는 순서와 같다.
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
    # 006/007이 만든 것. FK가 CASCADE라 005가 직접 안 지우지만 함께 사라진다.
    ("user_consents", "user_id"),
    ("password_reset_tokens", "user_id"),
    ("usage_events", "user_id"),
]


def literal(value) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return repr(value)
    return "'" + str(value).replace("'", "''") + "'"


def dump_rows(cur, out, table: str, where: str, params) -> int:
    cur.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position",
        (table,),
    )
    columns = [row[0] for row in cur.fetchall()]
    if not columns:
        return 0

    quoted = ", ".join(f'"{c}"' for c in columns)
    cur.execute(f"SELECT {quoted} FROM public.{table} WHERE {where}", params)
    rows = cur.fetchall()
    if not rows:
        return 0

    out.write(f"\n-- {table}: {len(rows)}행\n")
    for row in rows:
        values = ", ".join(literal(v) for v in row)
        out.write(f"INSERT INTO public.{table} ({quoted}) VALUES ({values});\n")
    return len(rows)


def main() -> int:
    url = os.getenv("POSTGRES_URL")
    if not url:
        print("POSTGRES_URL이 비어 있습니다. .env를 확인하세요.")
        return 1

    conn = psycopg2.connect(url)
    cur = conn.cursor()

    cur.execute(
        "SELECT id, username FROM public.users "
        "WHERE username IS NULL OR username = '' OR username = ANY(%s) ORDER BY id",
        (list(DOOMED_USERNAMES),),
    )
    doomed = cur.fetchall()
    doomed_ids = [row[0] for row in doomed]

    cur.execute("SELECT COUNT(*) FROM public.users")
    total = cur.fetchone()[0]
    survivors = total - len(doomed_ids)

    print(f"전체 계정 {total}개 중 {len(doomed_ids)}개가 삭제 대상, {survivors}개가 남습니다.")
    if survivors <= 0:
        print("남는 계정이 없습니다. 조건이 잘못됐을 수 있으니 중단합니다.")
        return 1
    if not doomed_ids:
        print("지울 것이 없습니다. 백업 파일을 만들지 않습니다.")
        return 0

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = ROOT / f"backup_before_005_{stamp}.sql"

    counts = {}
    with path.open("w", encoding="utf-8") as out:
        out.write("-- migration/005 적용 전 백업\n")
        out.write(f"-- 뜬 시각(UTC): {datetime.now(timezone.utc).isoformat()}\n")
        out.write(f"-- 삭제 대상 계정 {len(doomed_ids)}개 / 남는 계정 {survivors}개\n")
        out.write("-- 되돌리려면 이 파일을 SQL editor에 붙여 실행한다.\n")
        out.write("BEGIN;\n")

        # 자식을 먼저 쓰면 부모가 없어 실패한다. users를 먼저 쓴다.
        counts["users"] = dump_rows(cur, out, "users", "id = ANY(%s)", (doomed_ids,))
        for table, column in CHILD_TABLES:
            n = dump_rows(cur, out, table, f"{column} = ANY(%s)", (doomed_ids,))
            if n:
                counts[f"{table}.{column}"] = n

        out.write("\nCOMMIT;\n")

    conn.close()

    print(f"\n백업 파일: {path.name}")
    for name, n in counts.items():
        print(f"  {name:34} {n}행")
    print(f"\n총 {sum(counts.values())}행을 저장했습니다.")
    print("이 파일은 개인정보를 담고 있습니다. git에 올리지 마세요(.gitignore에 넣어뒀습니다).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
