"""운영 DB(Supabase Postgres)의 데이터를 SQL 파일 하나로 떠두고, 그 파일이 실제로
복원되는지 리허설한다 (2026-09-09).

왜 필요한가
--------
무료 플랜에는 자동 백업이 없다. 그걸 README "알려진 제약"에 적어두고도 정기 덤프를
안 만들어 뒀는데, 2026-09-09에 프로젝트가 미사용으로 일시정지되면서 실제로 위험이
드러났다. 이번에는 데이터가 무사했지만 안내문에 **2027-10-14까지만 재개 가능**이라고
적혀 있었다. 그 뒤로는 다운로드만 되고 되살릴 수 없다.

지인 테스트로 들어온 계정·피드백·자랑 글·사용 로그는 여기에만 있다. 레시피와 영양
데이터는 공공데이터에서 다시 받을 수 있지만 사용자가 남긴 것은 다시 만들 수 없다.

무엇을 뜨나
--------
`public` 스키마의 모든 테이블을 INSERT 문으로 떠서 파일 하나에 쓴다. 다만
`ingredient_catalog`(30만 행)는 기본에서 뺀다 - 공공데이터 그대로라 다시 받을 수
있는데 매 회차 50MB를 더하기 때문이다. 필요하면 `--all`로 함께 뜬다.

스키마는 안 뜬다. `migration/`이 저장소에 있으므로 복원은 "마이그레이션을 순서대로
적용한 뒤 이 파일을 실행"이다.

값을 문자열로 조립하지 않고 psycopg2의 `mogrify`에 맡긴다. 따옴표·NULL·JSON·날짜를
직접 이스케이프하면 반드시 어딘가 틀리고, 틀린 백업은 없는 백업보다 나쁘다.

검증을 왜 이렇게 하나
--------
처음에는 "파일의 INSERT 줄 수 == 읽은 행 수"로 확인했다. **그 검사는 통과했지만 틀린
확인이었다.** 줄바꿈이 든 값(피드백 본문)은 INSERT 문이 여러 줄에 걸치고, 역슬래시가
든 값은 psycopg2가 `E'...'` 형식으로 내보낸다. 둘 다 정상 SQL인데 줄 단위 셈법으로는
깨진 것처럼 보이고, 반대로 값 안에 "INSERT INTO"로 시작하는 줄이 있으면 깨진 파일이
멀쩡해 보인다.

SQL을 더 잘 쪼개는 파서를 짜는 대신 **진짜 복원을 시켜본다.** 임시 스키마에 같은 구조의
빈 테이블을 만들고 이 파일을 통째로 실행한 뒤 행 수를 대조하고 롤백한다. 임시 스키마는
트랜잭션이 끝나면 사라지므로 운영 데이터를 건드리지 않는다. 그래서 INSERT 문은
스키마 이름을 붙이지 않고 쓰고, 파일 맨 위에서 `search_path`로 대상을 정한다.

사용법
--------
    .venv/Scripts/python.exe scripts/backup_db.py              # 뜨고 곧바로 리허설까지
    .venv/Scripts/python.exe scripts/backup_db.py --all        # 대용량 참고표까지 전부
    .venv/Scripts/python.exe scripts/backup_db.py --list       # 무엇을 뜰지만 보여준다
    .venv/Scripts/python.exe scripts/backup_db.py --no-verify  # 리허설 생략(빠르게)
    .venv/Scripts/python.exe scripts/backup_db.py --verify backups/backup_....sql

결과는 `backups/`에 쓴다(gitignore 대상 - 운영 데이터에는 이메일과 전화번호가 있다).
"""

import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

# 공공데이터를 그대로 적재한 것이라 잃어도 다시 만들 수 있고, 행 수가 커서 매번 뜨면
# 백업 파일만 비대해진다. 원본은 data/app.db에도 남아 있다.
BULK_REFERENCE_TABLES = {"ingredient_catalog"}

BACKUP_DIR = ROOT / "backups"

# 파일 머리말에 테이블별 행 수를 적어둔다. 리허설이 이 숫자와 대조한다.
COUNT_COMMENT = re.compile(r"^--\s*rowcount\s+(\S+)\s+(\d+)\s*$", re.MULTILINE)


def list_tables(cur) -> list[str]:
    cur.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' "
        "ORDER BY table_name"
    )
    return [row[0] for row in cur.fetchall()]


def dump_table(cur, table: str, out) -> int:
    """테이블 하나를 INSERT 문으로 쓰고 쓴 행 수를 준다.

    스키마 이름을 안 붙이는 이유는 리허설 때문이다(모듈 주석 참고). 파일 맨 위의
    search_path가 대상을 정한다.
    """
    cur.execute(f'SELECT * FROM public."{table}"')
    columns = [d[0] for d in cur.description]
    column_sql = ", ".join(f'"{c}"' for c in columns)
    placeholders = ", ".join(["%s"] * len(columns))

    written = 0
    for row in cur:
        # 값 조립은 드라이버에 맡긴다. 손으로 이스케이프하면 반드시 어딘가 틀린다.
        values = cur.mogrify(placeholders, row).decode("utf-8")
        out.write(f'INSERT INTO "{table}" ({column_sql}) VALUES ({values});\n')
        written += 1
    return written


def write_backup(conn, include_all: bool) -> tuple[Path, dict[str, int]]:
    cur = conn.cursor()
    tables = list_tables(cur)
    skipped = [] if include_all else sorted(t for t in tables if t in BULK_REFERENCE_TABLES)
    targets = [t for t in tables if include_all or t not in BULK_REFERENCE_TABLES]

    print(f"대상 테이블 {len(targets)}개"
          + (f" (제외 {len(skipped)}개: {', '.join(skipped)})" if skipped else ""))

    BACKUP_DIR.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = BACKUP_DIR / f"backup_{stamp}.sql"

    counts: dict[str, int] = {}
    body_start = None
    with path.open("w", encoding="utf-8") as out:
        out.write(f"-- 냉장고 한끼 운영 DB 데이터 백업 ({stamp} UTC)\n--\n")
        out.write("-- 복원 순서:\n")
        out.write("--   1) 빈 Postgres에 migration/을 번호 순으로 적용한다(001~011).\n")
        out.write("--   2) 그 다음 이 파일을 실행한다.\n--\n")
        out.write("-- 스키마는 들어 있지 않다(migration/이 저장소에 있으므로).\n")
        if skipped:
            out.write(f"-- 제외한 참고 데이터: {', '.join(skipped)} (공공데이터라 재적재 가능)\n")
        out.write("--\n")
        out.write("-- 주의: 이 파일에는 이메일·전화번호 같은 개인정보가 들어 있다.\n")
        out.write("--       저장소에 커밋하거나 공유 폴더에 두지 말 것.\n--\n")
        out.write("-- 아래 rowcount 주석은 --verify 리허설이 대조에 쓴다. 지우지 말 것.\n")

        # 행 수를 먼저 세어 머리말에 적는다. 같은 스냅샷(REPEATABLE READ) 안이라 아래
        # 덤프와 어긋나지 않는다.
        for table in targets:
            cur.execute(f'SELECT count(*) FROM public."{table}"')
            counts[table] = cur.fetchone()[0]
            out.write(f"-- rowcount {table} {counts[table]}\n")

        out.write("\nSET search_path TO public;\n\n")
        body_start = out.tell()

        actual: dict[str, int] = {}
        for table in targets:
            out.write(f"-- ---- {table} ----\n")
            actual[table] = dump_table(cur, table, out)
            out.write("\n")

    mismatch = {t: (counts[t], actual[t]) for t in targets if counts[t] != actual[t]}
    if mismatch:
        print("머리말의 행 수와 실제로 쓴 행 수가 다릅니다:", mismatch)
    return path, counts


def verify(conn, path: Path) -> bool:
    """임시 스키마에 실제로 복원해보고 행 수를 대조한 뒤 되돌린다."""
    text = path.read_text(encoding="utf-8")
    expected = {t: int(n) for t, n in COUNT_COMMENT.findall(text)}
    if not expected:
        print("리허설 불가: 파일에 rowcount 주석이 없습니다.")
        return False

    schema = "backup_rehearsal"
    cur = conn.cursor()
    try:
        cur.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        cur.execute(f"CREATE SCHEMA {schema}")
        for table in expected:
            # INCLUDING ALL을 쓴다. 처음에는 DEFAULTS와 CONSTRAINTS만 넣었는데, 그러면
            # 기본키·UNIQUE 인덱스가 안 따라온다(Postgres에서 CONSTRAINTS는 CHECK만
            # 복사한다). 그 상태로는 같은 행이 두 번 든 손상된 백업이 리허설을 그냥
            # 통과한다. 외래키는 LIKE가 원래 안 가져오므로 테이블 순서는 신경 안 써도 된다.
            cur.execute(
                f'CREATE TABLE {schema}."{table}" (LIKE public."{table}" INCLUDING ALL)'
            )

        # 파일이 정하는 search_path 대신 임시 스키마를 보게 만든다.
        body = text.replace("SET search_path TO public;", f"SET search_path TO {schema};", 1)
        cur.execute(body)   # 파일 전체를 한 번에 실행한다. 이게 진짜 복원과 같은 경로다.

        ok = True
        for table, want in sorted(expected.items()):
            cur.execute(f'SELECT count(*) FROM {schema}."{table}"')
            got = cur.fetchone()[0]
            if got != want:
                print(f"    {table:26} 기대 {want} / 복원 {got}  <- 어긋남")
                ok = False
        return ok
    finally:
        # 임시 스키마도 넣은 행도 전부 되돌린다. 운영 데이터는 손대지 않았다.
        conn.rollback()


def main() -> int:
    if not os.getenv("POSTGRES_URL"):
        print("POSTGRES_URL이 비어 있습니다. .env를 확인하세요.")
        return 1

    # --verify <파일>: 이미 있는 백업만 검사한다.
    if "--verify" in sys.argv:
        idx = sys.argv.index("--verify")
        if idx + 1 >= len(sys.argv):
            print("사용법: --verify <백업파일경로>")
            return 1
        target = Path(sys.argv[idx + 1])
        conn = psycopg2.connect(os.environ["POSTGRES_URL"])
        print(f"리허설: {target}")
        ok = verify(conn, target)
        conn.close()
        print("복원 리허설 통과 - 이 파일로 되살릴 수 있다." if ok else "복원 리허설 실패.")
        return 0 if ok else 1

    include_all = "--all" in sys.argv
    conn = psycopg2.connect(os.environ["POSTGRES_URL"])

    if "--list" in sys.argv:
        cur = conn.cursor()
        tables = list_tables(cur)
        for table in tables:
            if not include_all and table in BULK_REFERENCE_TABLES:
                continue
            cur.execute(f'SELECT count(*) FROM public."{table}"')
            print(f"    {table:26} {cur.fetchone()[0]:>8}행")
        conn.close()
        return 0

    # 덤프 도중 다른 쓰기가 섞이면 테이블끼리 어긋난 백업이 된다. 한 시점을 고정한다.
    conn.set_session(readonly=True, isolation_level="REPEATABLE READ")
    path, counts = write_backup(conn, include_all)
    conn.close()

    size_mb = path.stat().st_size / 1024 / 1024
    print(f"\n파일: {path.relative_to(ROOT)}  ({size_mb:.1f}MB)")
    for table, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"    {table:26} {n:>8}행")
    print(f"  합계 {sum(counts.values())}행")

    if "--no-verify" in sys.argv:
        print("\n--no-verify: 복원 리허설을 건너뛰었다. 이 파일이 복원된다는 확인은 아직 없다.")
        return 0

    print("\n복원 리허설 중 (임시 스키마에 실제로 부어넣고 되돌린다)...")
    conn = psycopg2.connect(os.environ["POSTGRES_URL"])
    ok = verify(conn, path)
    conn.close()
    print("리허설 통과 - 이 파일로 되살릴 수 있다." if ok else "리허설 실패 - 이 백업을 믿지 마세요.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
