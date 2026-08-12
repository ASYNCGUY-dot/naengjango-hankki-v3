"""
API 라우터 계층을 검증하는 pytest 테스트의 공통 fixture.

tests/fixtures/seed.sql(스키마 + 최소 참고 데이터)로 매 테스트 세션마다 완전히 새
sqlite 파일을 만들어 쓴다. 로컬의 data/app.db(68MB, gitignore됨)에는 전혀 의존하지
않으므로 로컬과 CI(GitHub Actions) 어디서나 똑같이 재현된다.

테스트마다 커넥션을 새로 열고 트랜잭션 하나로 묶어서, 테스트가 끝나면 그 트랜잭션
전체를 롤백한다 - 그래서 테스트끼리 서로 데이터에 영향을 주지 않고, seed.sql로 만든
파일도 프로덕션 Postgres도 전혀 건드리지 않는다.
"""

import shutil
import sqlite3
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

SEED_SQL = Path(__file__).resolve().parent / "fixtures" / "seed.sql"


@pytest.fixture(scope="session")
def test_db_path():
    tmp_dir = tempfile.mkdtemp(prefix="naengjango_test_db_")
    tmp_path = Path(tmp_dir) / "test_app.db"
    conn = sqlite3.connect(tmp_path)
    conn.executescript(SEED_SQL.read_text(encoding="utf-8"))
    conn.commit()
    conn.close()
    yield tmp_path
    shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.fixture()
def client(test_db_path):
    from api import deps as api_deps
    from api import main as api_main

    # FastAPI가 동기 라우트를 스레드풀 워커에서 실행하기 때문에, fixture를 만든 스레드와
    # 실제 요청을 처리하는 스레드가 다르다 - check_same_thread=False로 풀어준다.
    # 테스트 하나당 요청을 순차적으로만 보내므로 동시 접근 걱정은 없다.
    # isolation_level=None으로 sqlite3 모듈의 자동 트랜잭션 관리를 끄고, BEGIN/rollback을
    # 직접 제어한다 - 테스트 하나 전체를 트랜잭션 하나로 묶어서, "signup 후 login" 같은
    # 여러 요청에 걸친 흐름에서는 이전 요청의 변경사항이 그대로 보이게 하고, 테스트가
    # 끝나면 그 트랜잭션 전체를 한 번에 롤백해 다음 테스트로 오염을 넘기지 않는다.
    conn = sqlite3.connect(test_db_path, check_same_thread=False, isolation_level=None)
    conn.execute("BEGIN")

    def override_get_db():
        cur = conn.cursor()
        try:
            yield cur
        finally:
            cur.close()

    api_main.app.dependency_overrides[api_deps.get_db] = override_get_db
    with TestClient(api_main.app) as c:
        yield c
    api_main.app.dependency_overrides.clear()
    conn.rollback()
    conn.close()
