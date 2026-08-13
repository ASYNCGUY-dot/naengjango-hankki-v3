"""
Mail Agent - Gmail SMTP로 메일을 보낸다 (2026-08-13).

V2의 notify_agent.py(작업 완료 알림용)를 비밀번호 초기화 메일 발송에 맞게 다시 쓴 것이다.
그 파일은 어디서도 쓰이지 않아 V3 정리 때 지웠는데, 초기화 기능이 생기면서 발송 수단이
필요해졌다. 지운 코드는 git 이력(285488c)에 남아 있어 그대로 되살렸다.

방식은 그대로다. Gmail 계정의 "앱 비밀번호"로 SMTP 발송한다. OAuth 연동이 아니라
발신 전용 비밀번호 하나만 있으면 되는 가장 단순한 방법이고, 무료다.

.env에 필요한 값:
    GMAIL_APP_PASSWORD    구글 앱 비밀번호 16자리 (2단계 인증이 켜져 있어야 발급된다)
    GMAIL_SENDER_ADDRESS  발신 주소

주의: 발송 실패가 요청 전체를 실패시키면 안 된다. 비밀번호 초기화 요청은 계정이 있든
없든 같은 응답을 돌려줘야 하는데(계정 존재 여부를 노출하지 않기 위해), 발송 실패로
500이 나면 그 구분이 새어나간다. 그래서 예외를 던지지 않고 (성공 여부, 사유)를 돌려준다.
"""

import os
import smtplib
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr

from dotenv import load_dotenv

load_dotenv()

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465  # SSL. 587(STARTTLS)보다 코드가 단순하다.
SMTP_TIMEOUT_SECONDS = 20

SENDER_NAME = "냉장고 한끼"


def _app_password() -> str | None:
    raw = os.getenv("GMAIL_APP_PASSWORD")
    if not raw:
        return None
    # 구글은 4자리씩 띄어서 보여주지만 로그인에는 공백 없는 16자리가 필요하다.
    return raw.replace(" ", "")


def is_configured() -> bool:
    return bool(_app_password() and os.getenv("GMAIL_SENDER_ADDRESS"))


def send_mail(to_address: str, subject: str, body: str) -> tuple[bool, str]:
    """메일을 보낸다. 실패해도 예외를 던지지 않고 (False, 사유)를 돌려준다."""
    password = _app_password()
    sender = os.getenv("GMAIL_SENDER_ADDRESS")
    if not password or not sender:
        return False, "GMAIL_APP_PASSWORD 또는 GMAIL_SENDER_ADDRESS가 비어 있습니다."

    message = MIMEText(body, "plain", "utf-8")
    message["Subject"] = Header(subject, "utf-8")
    message["From"] = formataddr((str(Header(SENDER_NAME, "utf-8")), sender))
    message["To"] = to_address

    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT_SECONDS) as smtp:
            smtp.login(sender, password)
            smtp.sendmail(sender, [to_address], message.as_string())
        return True, "발송 완료"
    except Exception as error:  # noqa: BLE001 - 어떤 실패든 요청을 중단시키지 않는다
        return False, f"발송 실패: {type(error).__name__}"


def build_password_reset_mail(reset_url: str, valid_minutes: int) -> tuple[str, str]:
    """초기화 안내 메일의 제목과 본문을 만든다.

    본문에 아이디나 이름을 넣지 않는다. 메일이 잘못된 주소로 갔을 때 그 계정의 정보가
    함께 새어나가기 때문이다. 링크와 유효시간만 담는다.
    """
    subject = "[냉장고 한끼] 비밀번호 초기화 안내"
    body = (
        "안녕하세요, 냉장고 한끼입니다.\n\n"
        "아래 링크에서 새 비밀번호를 설정할 수 있습니다.\n\n"
        f"{reset_url}\n\n"
        f"이 링크는 {valid_minutes}분 동안만 유효하며, 한 번 사용하면 다시 쓸 수 없습니다.\n"
        "본인이 요청하지 않았다면 이 메일을 무시하셔도 됩니다. "
        "링크를 사용하지 않으면 비밀번호는 그대로 유지됩니다.\n"
    )
    return subject, body
