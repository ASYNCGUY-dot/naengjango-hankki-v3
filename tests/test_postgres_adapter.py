"""진짜 Postgres에서만 드러나는 것들을 검증한다 (V3 Phase 1, 2026-08-12).

왜 필요한가
나머지 테스트는 전부 sqlite로 돈다(tests/conftest.py). 빠르고 .env 없이도 재현되지만,
운영은 Postgres라서 그 사이의 괴리가 테스트를 통과한 채 프로덕션에 나갈 수 있다.
실제로 V2에서 그런 일이 있었다 - psycopg2가 SQL 안의 리터럴 %를 파라미터
플레이스홀더로 오인해 IndexError를 냈는데, sqlite로 도는 로컬 테스트는 전부 초록이었다.

이 파일이 덮는 것은 두 가지다.
  1) 마이그레이션 체인이 빈 DB에서 처음부터 재생되는가 - 파일을 써두기만 하고 아무도
     실행해보지 않으면, 운영에 적용하는 그 순간이 첫 실행이 된다
  2) SqliteStyleCursor(?->%s 변환 어댑터)가 진짜 Postgres에서 기대대로 동작하는가

실행 조건
TEST_POSTGRES_URL이 설정돼 있을 때만 돈다. 없으면 통째로 건너뛴다 - 로컬에서 Docker
없이 pytest를 돌려도 나머지 104개는 그대로 통과해야 하기 때문이다.

경고: 이 파일은 대상 DB의 public 스키마를 통째로 지우고 다시 만든다. 그래서 접속
주소가 localhost가 아니면 아예 실행을 거부한다(아래 _assert_disposable). 운영 주소를
실수로 넣어도 데이터가 날아가지 않게 하기 위한 것이다.
"""

import os
from pathlib import Path
from urllib.parse import urlparse

import psycopg2
import pytest

from api.deps import SqliteStyleCursor

TEST_POSTGRES_URL = os.getenv("TEST_POSTGRES_URL")

pytestmark = pytest.mark.skipif(
    not TEST_POSTGRES_URL,
    reason="TEST_POSTGRES_URL이 없다 - Postgres 전용 검증은 건너뛴다",
)

MIGRATION_DIR = Path(__file__).resolve().parent.parent / "migration"

# 목록을 손으로 관리하지 않는다. 실제로 006을 추가하고도 여기 넣는 것을 잊어서, CI가
# 그 파일을 한 번도 검사하지 않은 채로 지나갔다. 디렉터리에서 읽으면 빠뜨릴 수 없다.
# 002는 sqlite 원본에서 데이터를 옮기는 파이썬 스크립트라 .sql만 모으면 자연히 빠진다.
MIGRATIONS = sorted(path.name for path in MIGRATION_DIR.glob("*.sql"))

DISPOSABLE_HOSTS = {"localhost", "127.0.0.1", "::1", "postgres"}


def _assert_disposable(url: str):
    host = urlparse(url).hostname or ""
    if host not in DISPOSABLE_HOSTS:
        raise RuntimeError(
            f"TEST_POSTGRES_URL의 호스트가 '{host}'다. 이 테스트는 public 스키마를 "
            f"통째로 지우므로 버려도 되는 로컬/CI DB에서만 돌린다."
        )


@pytest.fixture(scope="session")
def pg_conn():
    _assert_disposable(TEST_POSTGRES_URL)
    conn = psycopg2.connect(TEST_POSTGRES_URL)
    # 마이그레이션 파일이 자기 BEGIN/COMMIT을 갖고 있으므로(005) 트랜잭션을 파일에 맡긴다.
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("DROP SCHEMA IF EXISTS public CASCADE")
    cur.execute("CREATE SCHEMA public")
    for name in MIGRATIONS:
        sql = (MIGRATION_DIR / name).read_text(encoding="utf-8")
        cur.execute(sql)
    cur.close()
    yield conn
    conn.close()


@pytest.fixture()
def pg_cur(pg_conn):
    """운영과 같은 어댑터 커서. 테스트마다 롤백해서 서로 오염시키지 않는다."""
    pg_conn.autocommit = False
    cur = pg_conn.cursor(cursor_factory=SqliteStyleCursor)
    yield cur
    cur.close()
    pg_conn.rollback()
    pg_conn.autocommit = True


# ---------- 1) 마이그레이션 체인 ----------

def test_migration_chain_replays_on_an_empty_database(pg_conn):
    """pg_conn fixture가 001~005를 순서대로 적용한 것 자체가 검증이다.
    여기서는 결과 스키마가 코드가 기대하는 모양인지 확인한다."""
    cur = pg_conn.cursor()
    cur.execute("""
        SELECT column_name, is_nullable FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'auth_tokens'
        ORDER BY column_name
    """)
    columns = dict(cur.fetchall())
    # 004가 만든 모양 - expires_at이 없으면 만료 판단 자체가 안 된다.
    assert columns.get("expires_at") == "NO"
    assert columns.get("user_id") == "NO"

    cur.execute("""
        SELECT column_name, is_nullable FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'users'
          AND column_name IN ('username', 'password_hash')
        ORDER BY column_name
    """)
    user_columns = dict(cur.fetchall())
    assert user_columns == {"password_hash": "NO", "username": "NO"}
    cur.close()


def test_every_migration_file_is_replayed(pg_conn):
    """migration/의 .sql이 하나라도 빠지면 그 파일은 검증 없이 운영에 적용된다."""
    on_disk = sorted(path.name for path in MIGRATION_DIR.glob("*.sql"))
    assert MIGRATIONS == on_disk
    assert len(MIGRATIONS) >= 5


def test_a_failing_usage_log_does_not_discard_the_users_write(pg_cur):
    """사용 로그가 실패해도 같은 요청의 진짜 쓰기는 살아남아야 한다 (2026-08-18).

    이건 sqlite로는 증명이 안 된다. sqlite는 문 하나가 실패해도 트랜잭션을 그대로 두지만
    Postgres는 트랜잭션 전체를 중단 상태로 만든다. 그 상태에서는 뒤따르는 COMMIT이
    사실상 ROLLBACK이 되어, 사용자가 방금 넣은 재료가 조용히 사라진다.
    api/usage_log.py가 INSERT를 SAVEPOINT로 감싸는 이유가 정확히 이것이다.

    세이브포인트를 빼면 아래 SELECT가 InFailedSqlTransaction으로 터진다.
    """
    from api import usage_log

    pg_cur.execute(
        "INSERT INTO users (username, password_hash) VALUES (?, ?) RETURNING id",
        ("savepoint_probe", "x"),
    )
    user_id = pg_cur.fetchone()[0]

    # 흉내가 아니라 진짜로 터뜨린다. DDL도 트랜잭션 안이라 테스트 끝에 롤백된다.
    pg_cur.execute("DROP TABLE usage_events")
    usage_log.record(pg_cur, usage_log.PANTRY_ADD, user_id=user_id)

    pg_cur.execute("SELECT username FROM users WHERE id = ?", (user_id,))
    assert pg_cur.fetchone()[0] == "savepoint_probe"


def test_account_fields_exist_after_migration_006(pg_conn):
    """006이 실제로 적용됐는지 - 이름·연락처·이메일·가입시각과 동의/초기화 테이블."""
    cur = pg_conn.cursor()
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema='public' AND table_name='users'
          AND column_name IN ('name','phone','email','created_at')
    """)
    assert {row[0] for row in cur.fetchall()} == {"name", "phone", "email", "created_at"}

    cur.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema='public' AND table_name IN ('user_consents','password_reset_tokens')
    """)
    assert {row[0] for row in cur.fetchall()} == {"user_consents", "password_reset_tokens"}
    cur.close()


def test_email_is_unique_case_insensitively(pg_conn):
    """대소문자만 다른 주소를 다른 사람으로 보면 초기화 대상을 특정할 수 없다."""
    cur = pg_conn.cursor()
    try:
        cur.execute(
            "INSERT INTO users (username, password_hash, email) "
            "VALUES ('u_ci_a','x$y','Dup@Example.com')"
        )
        with pytest.raises(psycopg2.errors.UniqueViolation):
            cur.execute(
                "INSERT INTO users (username, password_hash, email) "
                "VALUES ('u_ci_b','x$y','dup@example.com')"
            )
    finally:
        # pg_conn은 autocommit이라 남긴 행이 다음 테스트까지 간다.
        cur.execute("DELETE FROM users WHERE username IN ('u_ci_a','u_ci_b')")
        cur.close()


def test_username_unique_constraint_exists(pg_conn):
    cur = pg_conn.cursor()
    cur.execute("""
        SELECT COUNT(*) FROM pg_constraint
        WHERE conrelid = 'public.users'::regclass AND contype = 'u'
          AND pg_get_constraintdef(oid) LIKE '%username%'
    """)
    assert cur.fetchone()[0] == 1, "005가 걸어야 할 username UNIQUE 제약이 없다"
    cur.close()


def test_auth_tokens_cascade_on_user_delete(pg_conn):
    """004가 건 ON DELETE CASCADE - 계정을 지우면 토큰도 함께 사라져야 한다."""
    cur = pg_conn.cursor()
    cur.execute(
        "INSERT INTO users (username, password_hash) VALUES ('cascade_target', 'x$y') RETURNING id"
    )
    user_id = cur.fetchone()[0]
    cur.execute(
        "INSERT INTO auth_tokens (token_hash, user_id, created_at, expires_at) "
        "VALUES ('hash_cascade', %s, '2026-08-12T00:00:00+00:00', '2026-09-11T00:00:00+00:00')",
        (user_id,),
    )
    cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
    cur.execute("SELECT COUNT(*) FROM auth_tokens WHERE token_hash = 'hash_cascade'")
    assert cur.fetchone()[0] == 0
    cur.close()


# ---------- 2) SqliteStyleCursor 어댑터 ----------

def test_question_mark_placeholders_are_converted(pg_cur):
    pg_cur.execute(
        "INSERT INTO users (username, password_hash) VALUES (?, ?)", ("adapter_user", "s$h")
    )
    pg_cur.execute("SELECT username FROM users WHERE username = ?", ("adapter_user",))
    assert pg_cur.fetchone()[0] == "adapter_user"


def test_lastrowid_returns_the_generated_id(pg_cur):
    """sqlite의 lastrowid를 SELECT lastval()로 흉내 낸 부분 - agent 코드가 이걸 그대로 쓴다."""
    pg_cur.execute(
        "INSERT INTO users (username, password_hash) VALUES (?, ?)", ("lastrowid_user", "s$h")
    )
    new_id = pg_cur.lastrowid
    pg_cur.execute("SELECT username FROM users WHERE id = ?", (new_id,))
    assert pg_cur.fetchone()[0] == "lastrowid_user"


def test_like_pattern_must_be_bound_as_a_parameter(pg_cur):
    """8.1 함정의 올바른 사용법. 패턴의 %를 파라미터로 넘기면 문제가 없다."""
    pg_cur.execute(
        "INSERT INTO recipes (menu_name, category, source_api, status) "
        "VALUES (?, ?, ?, 'approved')",
        ("말린 표고버섯 볶음", "반찬", "test"),
    )
    pg_cur.execute("SELECT menu_name FROM recipes WHERE menu_name LIKE ?", ("%말린%",))
    assert pg_cur.fetchone()[0] == "말린 표고버섯 볶음"


def test_literal_percent_with_params_still_breaks(pg_cur):
    """8.1 함정 자체를 못박아 둔다.

    파라미터를 함께 넘기면서 SQL 문자열에 리터럴 %를 박으면, psycopg2가 그 %를
    플레이스홀더로 오인한다. 어댑터가 이걸 고쳐주지는 않는다 - 고치려면 %를 %%로
    이스케이프해야 하는데, 그러면 파라미터 없이 실행되는 경우가 깨진다.
    그래서 "LIKE 패턴은 파라미터로 바인딩한다"는 규칙을 지키는 쪽이 답이다.
    이 테스트는 그 규칙이 왜 필요한지를 코드로 남겨둔다.
    """
    with pytest.raises(Exception):
        pg_cur.execute(
            "SELECT menu_name FROM recipes WHERE menu_name LIKE '%말린%' AND id > ?", (0,)
        )


# ---------- 3) 실제 agent 경로 ----------

def test_search_all_recipes_runs_on_postgres(pg_cur):
    """8.1 버그가 실제로 터졌던 경로다 - 키워드 검색이 LIKE를 쓴다."""
    from src.agents import recommendation_agent

    pg_cur.execute(
        "INSERT INTO recipes (menu_name, category, calorie, source_api, status) "
        "VALUES (?, ?, ?, ?, 'approved')",
        ("두부조림", "반찬", 180, "test"),
    )
    rows = recommendation_agent.search_all_recipes(pg_cur, keyword="두부", limit=10)
    assert any(r["menu_name"] == "두부조림" for r in rows)

    assert recommendation_agent.count_all_recipes(pg_cur, keyword="두부") >= 1


def test_recommendation_pipeline_runs_on_postgres(pg_cur):
    """후보 조회와 점수 계산이 쓰는 IN 절 배치 쿼리가 Postgres에서도 도는지 확인한다."""
    from src.agents import recommendation_agent

    pg_cur.execute(
        "INSERT INTO recipes (menu_name, category, calorie, source_api, status) "
        "VALUES (?, ?, ?, ?, 'approved')",
        ("고등어무조림", "일품", 320, "test"),
    )
    recipe_id = pg_cur.lastrowid
    for tag_type, tag_value in [("ingredient", "고등어"), ("ingredient", "무"),
                                 ("nutrition_group", "단백질")]:
        pg_cur.execute(
            "INSERT INTO recipe_tags (recipe_id, tag_type, tag_value) VALUES (?, ?, ?)",
            (recipe_id, tag_type, tag_value),
        )
    pg_cur.execute(
        "INSERT INTO recipe_ingredients (recipe_id, name, amount, unit) VALUES (?, ?, ?, ?)",
        (recipe_id, "고등어", 200.0, "g"),
    )

    candidates = recommendation_agent.get_candidate_recipes(pg_cur, {"allergy": ""})
    assert any(c["id"] == recipe_id for c in candidates)

    scored = recommendation_agent.score_by_ingredients(pg_cur, candidates, ["고등어"])
    target = next(c for c in scored if c["id"] == recipe_id)
    assert target["ingredient_overlap"] >= 1
    assert target["matched_weight"] >= 200.0


def test_concurrent_recipe_views_leave_one_row(pg_conn, monkeypatch):
    """동시에 처리된 두 열람이 한 줄만 남는다 (2026-09-15, migration/012).

    운영에서 같은 사람·같은 레시피가 15ms 간격으로 두 번 찍혔다. 동시 요청은 서로 커밋
    전이라 "있는지 보고 넣기"로는 못 막고, 유니크 제약 + ON CONFLICT DO NOTHING이어야
    뒤의 요청이 앞의 커밋을 기다렸다가 아무것도 안 넣는다. 이건 sqlite로 증명이 안 된다 -
    sqlite는 쓰기를 파일 단위로 잠가 동시성 자체가 운영과 다르다.

    두 연결을 실제로 겹치게 만든다. a가 넣고 커밋 전에 b가 넣으면 b는 멈춰야 하고, a가
    커밋하면 b는 아무것도 안 넣고 끝나야 한다. 제약이 없으면 b가 곧바로 넣고 두 줄이 된다.
    """
    import threading
    from datetime import datetime, timezone

    from api import usage_log

    class FixedClock:
        @staticmethod
        def now(tz=None):
            return datetime(2026, 9, 15, 12, 0, 1, tzinfo=timezone.utc)

    monkeypatch.setattr(usage_log, "datetime", FixedClock)

    setup = pg_conn.cursor()  # autocommit
    setup.execute(
        "INSERT INTO users (username, password_hash) VALUES ('dedupe_probe', 'x$y') RETURNING id"
    )
    user_id = setup.fetchone()[0]

    a = psycopg2.connect(TEST_POSTGRES_URL)
    b = psycopg2.connect(TEST_POSTGRES_URL)
    try:
        cur_a = a.cursor(cursor_factory=SqliteStyleCursor)
        cur_b = b.cursor(cursor_factory=SqliteStyleCursor)

        usage_log.record(cur_a, usage_log.RECIPE_VIEW, user_id=user_id, recipe_id=7)

        finished = threading.Event()

        def second_request():
            usage_log.record(cur_b, usage_log.RECIPE_VIEW, user_id=user_id, recipe_id=7)
            b.commit()
            finished.set()

        worker = threading.Thread(target=second_request)
        worker.start()
        assert not finished.wait(0.5), "b가 a의 커밋을 기다리지 않았다 - 제약이 없다"

        a.commit()
        worker.join(timeout=10)
        assert finished.is_set(), "a가 커밋한 뒤에도 b가 끝나지 않았다"

        setup.execute(
            "SELECT COUNT(*) FROM usage_events WHERE user_id = %s AND event = 'recipe_view'",
            (user_id,),
        )
        assert setup.fetchone()[0] == 1
    finally:
        a.close()
        b.close()
        setup.execute("DELETE FROM usage_events WHERE user_id = %s", (user_id,))
        setup.execute("DELETE FROM users WHERE id = %s", (user_id,))
        setup.close()


def test_different_recipes_in_one_window_stay_separate(pg_conn, monkeypatch):
    """묶는 단위는 (사람, 레시피)다. 사람만으로 묶으면 안 된다 (2026-09-17).

    인덱스에서 recipe_id를 빼도 위의 동시성 테스트는 그대로 통과한다 - 같은 레시피만
    보기 때문이다. 그 상태에서는 한 사람이 10초 안에 **서로 다른 레시피**를 열면 하나로
    묶여버려서, Phase 4의 "무엇을 실제로 열어봤나"가 통째로 어긋난다. 그 경계를 여기서
    고정한다(뮤테이션에서 실제로 살아남았던 구멍이다).
    """
    from datetime import datetime, timezone

    from api import usage_log

    class FixedClock:
        @staticmethod
        def now(tz=None):
            return datetime(2026, 9, 17, 12, 0, 1, tzinfo=timezone.utc)

    monkeypatch.setattr(usage_log, "datetime", FixedClock)

    setup = pg_conn.cursor()  # autocommit
    setup.execute(
        "INSERT INTO users (username, password_hash) VALUES ('two_recipes_probe', 'x$y') RETURNING id"
    )
    user_id = setup.fetchone()[0]

    conn = psycopg2.connect(TEST_POSTGRES_URL)
    try:
        cur = conn.cursor(cursor_factory=SqliteStyleCursor)
        usage_log.record(cur, usage_log.RECIPE_VIEW, user_id=user_id, recipe_id=11)
        usage_log.record(cur, usage_log.RECIPE_VIEW, user_id=user_id, recipe_id=22)
        conn.commit()

        setup.execute(
            "SELECT COUNT(*) FROM usage_events WHERE user_id = %s AND event = 'recipe_view'",
            (user_id,),
        )
        assert setup.fetchone()[0] == 2
    finally:
        conn.close()
        setup.execute("DELETE FROM usage_events WHERE user_id = %s", (user_id,))
        setup.execute("DELETE FROM users WHERE id = %s", (user_id,))
        setup.close()


def test_the_constraint_only_covers_recipe_views(pg_conn):
    """제약은 열람에만 걸려야 한다 (2026-09-17).

    지금은 코드가 열람 말고는 구간 번호를 안 붙이므로, 인덱스 조건에서 event를 빼도
    겉으로는 티가 안 난다(뮤테이션에서 살아남았다). 그래서 스키마를 직접 찌른다 -
    다른 이벤트에 번호가 붙은 채로 들어와도 묶이면 안 된다. 나중에 누가 다른 이벤트에
    중복 방지를 붙이려고 번호를 달면, 그 순간 조용히 기록이 사라지는 것을 여기서 막는다.
    """
    setup = pg_conn.cursor()  # autocommit
    setup.execute(
        "INSERT INTO users (username, password_hash) VALUES ('predicate_probe', 'x$y') RETURNING id"
    )
    user_id = setup.fetchone()[0]
    try:
        # recipe_id를 반드시 채운다. NULL로 두면 DB가 NULL끼리는 서로 다르다고 보아
        # 인덱스 조건과 무관하게 두 줄이 들어가고, 그러면 이 테스트가 아무것도 확인하지
        # 못한다(처음에 NULL로 썼다가 뮤테이션이 그대로 살아남아서 알았다).
        for _ in range(2):
            setup.execute(
                "INSERT INTO usage_events (user_id, event, recipe_id, created_at, dedupe_bucket) "
                "VALUES (%s, 'pantry_add', 33, '2026-09-17T12:00:01+00:00', 1)",
                (user_id,),
            )
        setup.execute(
            "SELECT COUNT(*) FROM usage_events WHERE user_id = %s AND event = 'pantry_add'",
            (user_id,),
        )
        assert setup.fetchone()[0] == 2
    finally:
        setup.execute("DELETE FROM usage_events WHERE user_id = %s", (user_id,))
        setup.execute("DELETE FROM users WHERE id = %s", (user_id,))
        setup.close()
