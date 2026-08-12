"""
Crypto Utils [확장] - 유저가 등록한 3자 API 키를 암호화해서 저장하기 위한 유틸 (#95)

왜 필요한가:
- 유저 본인 레시피가 정식 레시피로 승격되면, 그 레시피의 재료 구매 링크에 사이트 기본 키 대신
  유저 본인의 쿠팡파트너스 키를 써서 유저에게도 수익이 가게 만드는 기능(#95)을 추가한다.
- 이건 지수님 한 명의 키(.env, 평문 파일 하나만 있으면 됨)와 다르게, 여러 유저의 민감한 3자
  인증정보를 DB에 보관해야 하는 상황이라 평문 저장은 안 된다 - 반드시 암호화해서 저장하고,
  실제로 쓰는 그 순간에만 메모리에서 복호화한다.

사용법:
1. 아래 명령으로 마스터키를 한 번만 만든다(터미널에서 실행):
     python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
2. 나온 값을 .env에 APP_ENCRYPTION_KEY=그값 형태로 저장한다 (한 번 정하면 절대 바꾸면 안 된다 -
   바꾸면 이미 암호화해서 저장해둔 기존 값들을 더 이상 복호화할 수 없게 된다).
3. encrypt_value()/decrypt_value()만 가져다 쓰면 된다 - 저장할 때 encrypt_value(),
   실제로 쓸 때만 decrypt_value().
"""

import os
from dotenv import load_dotenv

load_dotenv()

_ENCRYPTION_KEY = os.getenv("APP_ENCRYPTION_KEY")


def _get_fernet():
    from cryptography.fernet import Fernet

    if not _ENCRYPTION_KEY:
        raise RuntimeError(
            "APP_ENCRYPTION_KEY가 .env에 없습니다. 아래 명령을 터미널에서 실행해서 나온 값을 "
            ".env에 APP_ENCRYPTION_KEY=발급된값 형태로 추가한 뒤 다시 시도하세요:\n"
            '  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        )
    return Fernet(_ENCRYPTION_KEY.encode())


def encrypt_value(plain_text: str) -> str:
    """평문(예: 쿠팡파트너스 Secret Key)을 암호문 문자열로 바꾼다. DB에는 이 결과만 저장한다."""
    if not plain_text:
        return ""
    return _get_fernet().encrypt(plain_text.encode()).decode()


def decrypt_value(cipher_text: str) -> str:
    """DB에 저장된 암호문을, 실제로 API 호출 등에 쓰는 그 순간에만 평문으로 되돌린다."""
    if not cipher_text:
        return ""
    return _get_fernet().decrypt(cipher_text.encode()).decode()
