"""배포 설정이 코드가 실제로 필요로 하는 것을 다 주는지 검증한다 (2026-08-18).

왜 필요한가
render.yaml이 넘겨주는 환경변수는 5개인데 api/·src/의 코드가 읽는 것은 15개였다.
빠진 것 중에 GMAIL_APP_PASSWORD와 WEB_BASE_URL이 있었고, 이게 특히 나빴던 이유는
비밀번호 초기화가 **조용히** 실패하기 때문이다. /auth/password-reset/request는 계정
존재 여부가 새어나가지 않도록 성공·실패에 관계없이 같은 응답을 준다. 그래서 사용자는
"메일을 보냈어요"를 보고 기다리는데 아무것도 오지 않고, 화면에도 응답에도 신호가 없다.

배포하고 지인이 눌러보기 전까지는 아무도 모르는 종류의 구멍이라, 사람이 눈으로
맞춰보는 대신 여기서 기계적으로 잡는다.
"""

import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parent.parent
RENDER_YAML = ROOT / "render.yaml"

# os.getenv("NAME") / os.environ["NAME"] / os.environ.get("NAME")
ENV_READ = re.compile(r"""os\.(?:getenv|environ(?:\.get)?)\(\s*["']([A-Z_0-9]+)["']""")

# 배포된 프로세스가 읽는 코드만 본다. scripts/는 일회성 적재 도구라 Render에서 돌지 않는다.
DEPLOYED_DIRS = ("api", "src")

# 값이 없어도 되는 것. 없으면 코드가 알아서 안전한 기본값을 쓴다.
OPTIONAL: set[str] = set()


def _declared_keys() -> set[str]:
    config = yaml.safe_load(RENDER_YAML.read_text(encoding="utf-8"))
    keys = set()
    for service in config["services"]:
        for entry in service.get("envVars", []):
            keys.add(entry["key"])
    return keys


def _env_vars_the_code_reads() -> dict[str, set[str]]:
    """환경변수 이름 -> 그것을 읽는 파일들."""
    found: dict[str, set[str]] = {}
    for directory in DEPLOYED_DIRS:
        for path in (ROOT / directory).rglob("*.py"):
            for name in ENV_READ.findall(path.read_text(encoding="utf-8")):
                found.setdefault(name, set()).add(str(path.relative_to(ROOT)))
    return found


def test_render_yaml_declares_every_env_var_the_code_reads():
    declared = _declared_keys()
    used = _env_vars_the_code_reads()

    missing = {
        name: sorted(files)
        for name, files in used.items()
        if name not in declared and name not in OPTIONAL
    }
    assert not missing, (
        "render.yaml에 선언되지 않은 환경변수가 있다. Render 대시보드에 값을 넣을 자리가 "
        f"아예 생기지 않으므로 배포하면 그 기능이 조용히 죽는다: {missing}"
    )


def test_the_regex_actually_finds_things():
    """위 테스트가 '아무것도 못 찾아서' 통과하는 상태를 막는다."""
    used = _env_vars_the_code_reads()
    assert "POSTGRES_URL" in used
    assert len(used) >= 10


def test_password_reset_env_is_declared():
    """조용히 실패하는 경로라 따로 못 박아둔다.

    이 셋 중 하나라도 빠지면 사용자는 초기화 메일을 영영 못 받으면서도 그 사실을
    알 방법이 없다.
    """
    declared = _declared_keys()
    for key in ("GMAIL_APP_PASSWORD", "GMAIL_SENDER_ADDRESS", "WEB_BASE_URL"):
        assert key in declared, f"{key}가 render.yaml에 없다"


def test_web_base_url_is_not_left_at_localhost():
    """메일 본문의 링크가 받는 사람의 컴퓨터를 가리키면 안 된다."""
    config = yaml.safe_load(RENDER_YAML.read_text(encoding="utf-8"))
    for service in config["services"]:
        for entry in service.get("envVars", []):
            if entry["key"] == "WEB_BASE_URL":
                value = entry.get("value", "")
                assert value.startswith("https://"), f"WEB_BASE_URL이 {value!r}이다"
                assert "localhost" not in value
