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
import sqlite3
from collections.abc import Generator

import psycopg2
import psycopg2.extensions
import psycopg2.pool
from dotenv import load_dotenv

load_dotenv()
POSTGRES_URL = os.getenv("POSTGRES_URL")

# UNIQUE 같은 제약 위반은 드라이버마다 다른 예외 클래스로 온다(테스트는 sqlite,
# 운영은 Postgres). 라우터가 한 번에 잡을 수 있도록 여기서 묶는다 - 두 드라이버의
# 차이를 흡수하는 것이 이 파일의 역할이다.
INTEGRITY_ERRORS = (sqlite3.IntegrityError, psycopg2.IntegrityError)


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
        # POSTGRES_URL이 비면 psycopg2가 기본값인 localhost:5432로 붙으려 하고, 오류는
        # "연결 거부"로 나온다. 그러면 원인이 .env를 못 읽은 것이라는 걸 알아채기 어렵다.
        # 실제로 그렇게 한참 헤맸으므로 여기서 무엇이 없는지 그대로 말해준다.
        if not POSTGRES_URL:
            raise RuntimeError(
                "POSTGRES_URL이 비어 있습니다. .env를 읽지 못했을 가능성이 큽니다 "
                "(uvicorn을 저장소 밖에서 띄우면 인자 없는 load_dotenv()가 .env를 못 찾습니다)."
            )
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
