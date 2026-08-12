"""
API 공통 의존성 - 요청마다 커넥션 풀에서 연결을 빌려주고 돌려받는다.
Postgres(Supabase)로 전환 완료.

에이전트 파일(src/agents/*.py)은 전부 SQLite 스타일로 짜여 있어서
(자리표시자 "?", cur.lastrowid) 그대로 두고, 그 차이를 이 어댑터 계층에서 흡수한다:
  - SqliteStyleCursor.execute(): SQL 안의 "?"를 psycopg2가 쓰는 "%s"로 바꿔서 실행한다.
  - SqliteStyleCursor.lastrowid: sqlite3의 lastrowid를 흉내내서, INSERT 직후
    SELECT lastval()로 방금 생성된 시퀀스 값을 돌려준다.

커넥션 풀은 지연 생성한다(첫 get_db() 호출 시점에 생성) - 모듈을 그냥 import만
해도 즉시 Postgres에 연결을 시도하던 이전 방식은, POSTGRES_URL이 없는 환경(예:
pytest가 get_db를 오버라이드해서 실제로 DB에 붙지 않는 테스트, .env 없는 CI)에서
import 시점에 바로 크래시났다. tests/conftest.py 참고.
"""

import os
from collections.abc import Generator

import psycopg2
import psycopg2.extensions
import psycopg2.pool
from dotenv import load_dotenv

load_dotenv()
POSTGRES_URL = os.getenv("POSTGRES_URL")


class SqliteStyleCursor(psycopg2.extensions.cursor):
    def execute(self, query, vars=None):
        if isinstance(query, str) and "?" in query:
            query = query.replace("?", "%s")
        return super().execute(query, vars)

    def executemany(self, query, vars_list):
        if isinstance(query, str) and "?" in query:
            query = query.replace("?", "%s")
        return super().executemany(query, vars_list)

    @property
    def lastrowid(self):
        self.execute("SELECT lastval()")
        return self.fetchone()[0]


_pool: psycopg2.pool.ThreadedConnectionPool | None = None


def get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    global _pool
    if _pool is None:
        _pool = psycopg2.pool.ThreadedConnectionPool(minconn=1, maxconn=10, dsn=POSTGRES_URL)
    return _pool


def get_db() -> Generator[SqliteStyleCursor, None, None]:
    pool = get_pool()
    conn = pool.getconn()
    cur = conn.cursor(cursor_factory=SqliteStyleCursor)
    try:
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        pool.putconn(conn)
