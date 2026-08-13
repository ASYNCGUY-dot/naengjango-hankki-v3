"""이 저장소의 FastAPI 앱에서 OpenAPI 명세를 뽑아 frontend/openapi.json에 쓴다.

왜 배포된 서버가 아니라 로컬 코드에서 뽑는가
처음에는 배포된 V2 백엔드에서 받아 타입을 만들었는데, 그 명세에는 V3에서 이미 지운
POST /profile이 남아 있었다. 타입으로 프론트·백엔드 불일치를 잡겠다고 해놓고 정작
저장소 코드가 아닌 다른 것을 기준으로 삼은 셈이다. 이 저장소의 코드에서 뽑으면
타입이 항상 지금 코드와 같은 것을 가리킨다.

서버를 띄우지 않아도 된다. api/deps.py가 커넥션 풀을 지연 생성하도록 짜여 있어서
import만으로는 DB에 붙지 않는다.

사용법:
    ./.venv/Scripts/python.exe scripts/dump_openapi.py
    cd frontend && npm run gen:api
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from api.main import app  # noqa: E402

OUT_PATH = REPO_ROOT / "frontend" / "openapi.json"


def main() -> int:
    spec = app.openapi()
    # 들여쓰기를 고정해야 재생성했을 때 의미 없는 diff가 생기지 않는다.
    text = json.dumps(spec, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    OUT_PATH.write_text(text, encoding="utf-8")

    paths = spec.get("paths", {})
    operations = sum(
        1
        for methods in paths.values()
        for method in methods
        if method in {"get", "post", "put", "delete", "patch"}
    )
    print(f"{OUT_PATH.relative_to(REPO_ROOT)} 갱신")
    print(f"  경로 {len(paths)}개 / 오퍼레이션 {operations}개")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
