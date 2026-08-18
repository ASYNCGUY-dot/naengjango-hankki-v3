"""비밀번호 초기화 링크를 직접 만들어 준다 (2026-08-18).

왜 필요한가
Render 무료 웹 서비스가 SMTP 포트(25/465/587) 아웃바운드를 막아서 초기화 메일을 보낼
수 없다. 자격증명 문제가 아니다 - 같은 코드가 로컬에서는 2.5초에 발송된다.

그래서 Phase 4(지인 5명) 동안은 화면에서 메일 요청을 빼고, 비밀번호를 잊은 사람이
연락해오면 이 스크립트로 링크를 만들어 카카오톡 등으로 직접 전달한다. 다섯 명 규모에서
분실은 있어도 한두 번이라, 메일 서비스를 붙이는 것보다 이 편이 싸다.

서버 쪽 엔드포인트와 /reset-password 화면은 그대로 살아 있으므로, 받은 사람은 링크만
누르면 평소와 똑같이 새 비밀번호를 설정할 수 있다.

사용법:
    .venv/Scripts/python.exe scripts/make_reset_link.py <아이디 또는 이메일>

주의: 만들어진 링크는 그 계정의 비밀번호를 바꿀 수 있는 열쇠다. 본인이 맞는지 확인한
뒤에 전달할 것. 30분이 지나면 자동으로 만료된다.
"""

import os
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

from api.deps import SqliteStyleCursor  # noqa: E402
from src.agents import auth_agent  # noqa: E402

WEB_BASE_URL = os.getenv("WEB_BASE_URL", "https://naengjango-hankki-v3-web.onrender.com")


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 1
    who = sys.argv[1].strip()

    url = os.getenv("POSTGRES_URL")
    if not url:
        print("POSTGRES_URL이 비어 있습니다. .env를 확인하세요.")
        return 1

    conn = psycopg2.connect(url)
    cur = conn.cursor(cursor_factory=SqliteStyleCursor)

    # 아이디로도 이메일로도 찾게 한다. 연락해온 사람이 둘 중 무엇을 기억할지 모른다.
    cur.execute(
        "SELECT id, username, email FROM public.users "
        "WHERE username = ? OR LOWER(email) = LOWER(?)",
        (who, who),
    )
    rows = cur.fetchall()
    if not rows:
        print(f"'{who}'에 해당하는 계정이 없습니다.")
        conn.close()
        return 1
    if len(rows) > 1:
        print(f"'{who}'로 계정이 여러 개 나옵니다. 아이디로 다시 시도하세요: {rows}")
        conn.close()
        return 1

    user_id, username, email = rows[0]
    if not email:
        print(f"'{username}'에는 이메일이 없어 토큰을 만들 수 없습니다.")
        conn.close()
        return 1

    # 실제 초기화 흐름과 같은 함수를 쓴다. 여기서만 다른 토큰을 만들면 검증된 경로가 아니다.
    token = auth_agent.create_password_reset_token(cur, email)
    conn.commit()
    conn.close()

    if token is None:
        print("토큰 발급에 실패했습니다.")
        return 1

    minutes = int(auth_agent.RESET_TOKEN_TTL.total_seconds() // 60)
    print(f"\n계정: {username} (user {user_id})")
    print(f"유효시간: {minutes}분, 한 번 쓰면 만료\n")
    print(f"{WEB_BASE_URL}/reset-password?token={token}\n")
    print("본인이 맞는지 확인한 뒤 전달하세요. 이 링크로 비밀번호를 바꿀 수 있습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
