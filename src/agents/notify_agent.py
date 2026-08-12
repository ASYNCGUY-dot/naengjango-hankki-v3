"""
Notify Agent - 작업 완료 시 이메일 알림 (2026-07-15 추가)

- 역할: 큰 작업(리팩토링, 기능 추가, 리포트 갱신 등)이 끝났을 때 지수님 본인 이메일로
  "작업 완료" 알림 메일을 실제로 발송한다.
- 방식: Gmail 계정의 "앱 비밀번호"를 이용한 SMTP 발송. OAuth 연동이 아니라 이메일 계정의
  발신 전용 비밀번호 하나만 있으면 되는 가장 단순한 방식이다.
- 주의: 이 프로젝트의 다른 API 키들과 동일하게 .env에만 저장하고 절대 코드에 직접 적지 않는다.
  .env는 이미 .gitignore에 포함되어 있어 git에는 올라가지 않는다.

[.env에 필요한 값 - 아직 비어있으면 아래 순서로 채워야 한다]
GMAIL_APP_PASSWORD  - 구글 계정 "앱 비밀번호"(16자리, 공백 없이). 아래 순서로 발급:
    1) https://myaccount.google.com/security 접속 (본인 구글 계정으로 로그인한 상태)
    2) "2단계 인증"이 꺼져 있으면 먼저 켠다 (앱 비밀번호는 2단계 인증이 켜져 있어야 발급 가능)
    3) https://myaccount.google.com/apppasswords 접속
    4) 앱 이름에 "냉장고한끼 알림" 같은 이름을 적고 [만들기] 클릭
    5) 화면에 나오는 16자리 코드(공백 포함해서 보여지지만 실제로는 공백 없이 저장)를 복사
    6) .env 파일의 GMAIL_APP_PASSWORD= 뒤에 붙여넣기 (공백 없이)
GMAIL_SENDER_ADDRESS - 발신자 계정 주소 (보통 본인 Gmail 주소와 동일)
NOTIFY_EMAIL_TO      - 알림을 받을 주소 (본인 이메일이면 발신자와 같아도 된다)
"""

import os
import smtplib
from email.mime.text import MIMEText
from email.header import Header
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
if GMAIL_APP_PASSWORD:
    # 구글이 화면에 보여줄 때는 4자리씩 띄어서 보여주지만(예: "abcd efgh ijkl mnop"),
    # 실제 로그인에는 공백 없는 16자리가 필요하다. .env에 공백 포함해서 붙여넣었어도
    # 여기서 자동으로 제거해주므로 신경 쓰지 않아도 된다.
    GMAIL_APP_PASSWORD = GMAIL_APP_PASSWORD.replace(" ", "")
GMAIL_SENDER_ADDRESS = os.getenv("GMAIL_SENDER_ADDRESS")
NOTIFY_EMAIL_TO = os.getenv("NOTIFY_EMAIL_TO")

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465  # SSL 포트. 587(TLS)이 아니라 465(SSL)를 쓰면 코드가 한 줄 더 단순해진다.


def is_configured() -> bool:
    """.env에 필요한 값이 다 채워졌는지 확인한다. 하나라도 비어있으면 False."""
    return bool(GMAIL_APP_PASSWORD and GMAIL_SENDER_ADDRESS and NOTIFY_EMAIL_TO)


def send_notification(subject: str, body: str) -> tuple[bool, str]:
    """
    작업 완료 알림 메일을 실제로 발송한다.
    반환값: (성공 여부, 메시지) - 실패해도 예외를 던지지 않고 원인 문자열을 돌려준다
    (다른 agent들과 동일하게, 알림 발송 실패가 전체 작업을 중단시키면 안 되기 때문).
    """
    if not is_configured():
        return False, (
            "GMAIL_APP_PASSWORD / GMAIL_SENDER_ADDRESS / NOTIFY_EMAIL_TO 중 "
            ".env에 비어있는 값이 있습니다. 먼저 채워주세요."
        )

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    msg = MIMEText(f"{body}\n\n(발송 시각: {timestamp})", _charset="utf-8")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = GMAIL_SENDER_ADDRESS
    msg["To"] = NOTIFY_EMAIL_TO

    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.login(GMAIL_SENDER_ADDRESS, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_SENDER_ADDRESS, [NOTIFY_EMAIL_TO], msg.as_string())
        return True, "발송 완료"
    except Exception as e:
        # [디버그] 다른 agent들의 except Exception 패턴과 동일하게, 원인을 조용히 삼키지 않고
        # 문자열로 돌려줘서 호출한 쪽에서 "왜 안 갔는지" 바로 알 수 있게 한다.
        return False, f"발송 실패: {e}"


if __name__ == "__main__":
    # 터미널에서 "python src/agents/notify_agent.py" 로 직접 실행하면 테스트 메일이 나간다.
    ok, message = send_notification(
        "[냉장고 한끼] 알림 테스트",
        "이 메일이 보이면 이메일 알림 설정이 정상적으로 완료된 것입니다.",
    )
    print(f"{'성공' if ok else '실패'}: {message}")
