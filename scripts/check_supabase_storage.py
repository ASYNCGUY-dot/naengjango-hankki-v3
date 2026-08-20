"""Supabase Storage 설정이 실제로 되는지 확인한다 (2026-08-20).

자랑하기의 사진 업로드가 이 설정 위에 올라간다. 키를 넣고 바로 이걸 돌려서,
"버킷이 있는가 / 올라가는가 / 로그인 없이 보이는가 / 지워지는가"를 한 번에 본다.
설정이 틀렸을 때 화면을 만들다 알게 되면 원인이 코드인지 설정인지 구분하기 어렵다.

작은 png 하나를 올렸다가 지운다. 남기지 않는다.

사용법:
    .venv/Scripts/python.exe scripts/check_supabase_storage.py
"""

import base64
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

BUCKET = "brag-photos"

# 1x1 투명 png. 확인용이라 내용은 아무래도 상관없다.
TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
    "YPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"  {'OK  ' if ok else 'FAIL'} {label:40} {detail}")
    if not ok:
        failures.append(label)
    return ok


url = os.getenv("SUPABASE_URL", "").rstrip("/")
key = os.getenv("SUPABASE_SERVICE_KEY", "")

print("1) 환경변수")
if not check("SUPABASE_URL", bool(url), url or "비어 있음"):
    print("\n.env에 SUPABASE_URL을 넣어주세요. 예: https://xxxxx.supabase.co")
    sys.exit(1)
# 키 자체는 절대 찍지 않는다. 길이와 접두사만 본다.
prefix = key[:10] + "…" if key else "비어 있음"
if not check("SUPABASE_SERVICE_KEY", len(key) > 20, f"{prefix} ({len(key)}자)"):
    print("\n.env에 SUPABASE_SERVICE_KEY를 넣어주세요(secret 키. publishable 키가 아닙니다).")
    sys.exit(1)

headers = {"apikey": key, "Authorization": f"Bearer {key}"}
name = "check_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + ".png"

print("\n2) 버킷")
res = requests.get(f"{url}/storage/v1/bucket/{BUCKET}", headers=headers, timeout=30)
if not check(f"'{BUCKET}' 버킷이 있다", res.status_code == 200, str(res.status_code)):
    print(f"\n대시보드 Storage에서 '{BUCKET}' 버킷을 만들어주세요.")
    sys.exit(1)
is_public = res.json().get("public") is True
check("공개 버킷이다", is_public, "public=" + str(res.json().get("public")))

print("\n3) 올리기 / 보기 / 지우기")
res = requests.post(
    f"{url}/storage/v1/object/{BUCKET}/{name}",
    headers={**headers, "Content-Type": "image/png"},
    data=TINY_PNG,
    timeout=60,
)
uploaded = check("업로드", res.status_code in (200, 201), str(res.status_code))

if uploaded:
    public_url = f"{url}/storage/v1/object/public/{BUCKET}/{name}"
    # 인증 헤더 없이 받아본다. 화면의 <img>가 하는 것과 같은 요청이다.
    res = requests.get(public_url, timeout=30)
    check(
        "로그인 없이 보인다",
        res.status_code == 200 and res.content == TINY_PNG,
        f"{res.status_code}, {len(res.content)}바이트",
    )

    res = requests.delete(f"{url}/storage/v1/object/{BUCKET}/{name}", headers=headers, timeout=30)
    check("지우기(흔적 남기지 않기)", res.status_code == 200, str(res.status_code))

print()
if failures:
    print(f"실패 {len(failures)}건: {failures}")
    sys.exit(1)
print("전부 통과. 사진 업로드를 붙일 수 있습니다.")
