"""
Storage Agent - 자랑하기 사진을 Supabase Storage에 올린다 (2026-08-20).

Render 무료 웹 서비스는 디스크가 재시작마다 날아가서 파일을 둘 곳이 없다. 이미 쓰고
있는 Supabase에 무료 1GB 저장소가 딸려 오므로 그쪽에 올린다.

**키는 서버에만 둔다.** SUPABASE_SERVICE_KEY는 프로젝트 전체 권한을 가진 비밀키다.
브라우저가 Supabase에 직접 올리게 하려면 이 키를 내보내거나 RLS 정책을 따로 짜야
하는데, 우리는 이미 토큰 인증이 있으므로 서버가 대신 올리는 편이 단순하고 안전하다.

설정이 없으면 예외를 던지지 않고 None을 돌려준다. 사진 없이 글만 올리는 것은
정상 동작이라, 저장소가 없다고 자랑하기 기능 전체가 죽으면 안 된다.
"""

import logging
import os
import uuid
from datetime import datetime, timezone

import requests

_logger = logging.getLogger("src.agents.storage_agent")

BUCKET = "brag-photos"

# 버킷에도 같은 상한이 걸려 있지만 여기서 먼저 막는다. 2MB짜리를 Supabase까지
# 보내고 나서 거절당하면 무료 티어의 대역폭만 쓴다.
MAX_BYTES = 2 * 1024 * 1024

# 확장자는 신뢰할 수 없으므로 실제 바이트 앞부분(매직 넘버)으로 판별한다.
# 브라우저가 보낸 Content-Type도 마찬가지로 위조할 수 있다.
_SIGNATURES: list[tuple[bytes, str, str]] = [
    (b"\xff\xd8\xff", "image/jpeg", "jpg"),
    (b"\x89PNG\r\n\x1a\n", "image/png", "png"),
]


def is_configured() -> bool:
    return bool(os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SERVICE_KEY"))


def detect_image(data: bytes) -> tuple[str, str] | None:
    """이미지면 (mime, 확장자), 아니면 None.

    webp는 앞 4바이트가 "RIFF"이고 8~12바이트가 "WEBP"라 따로 본다.
    """
    for signature, mime, ext in _SIGNATURES:
        if data.startswith(signature):
            return mime, ext
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", "webp"
    return None


def upload_image(data: bytes, user_id: int) -> str | None:
    """사진 한 장을 올리고 공개 주소를 돌려준다. 설정이 없거나 실패하면 None.

    파일 이름에 uuid를 넣는다. 사용자가 준 이름을 쓰면 경로 조작이 가능하고,
    같은 이름이 서로를 덮어쓴다.
    """
    if not is_configured():
        _logger.warning("storage_agent: SUPABASE_URL/KEY가 없어 업로드를 건너뛴다")
        return None

    detected = detect_image(data)
    if detected is None:
        return None
    mime, ext = detected

    base = os.environ["SUPABASE_URL"].rstrip("/")
    key = os.environ["SUPABASE_SERVICE_KEY"]
    # 누가 올렸는지와 언제인지를 경로에 남긴다. 나중에 한 사람 것만 지우기 쉽다.
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    path = f"{user_id}/{stamp}_{uuid.uuid4().hex}.{ext}"

    try:
        res = requests.post(
            f"{base}/storage/v1/object/{BUCKET}/{path}",
            headers={"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": mime},
            data=data,
            timeout=60,
        )
    except Exception:  # noqa: BLE001
        _logger.warning("storage_agent: 업로드 요청 실패", exc_info=True)
        return None

    if res.status_code not in (200, 201):
        _logger.warning("storage_agent: 업로드 거절 %s %s", res.status_code, res.text[:200])
        return None

    return f"{base}/storage/v1/object/public/{BUCKET}/{path}"
