"""테스트에서 공통으로 쓰는 요청 본문 만들기.

V3에서 가입에 필요한 정보가 늘었다(이름·연락처·이메일·성별·연령대·동의). 테스트마다
그 값을 다 적으면 정작 그 테스트가 무엇을 검증하는지가 안 보이고, 가입 항목이 또 바뀌면
파일 12개를 다시 고쳐야 한다. 기본값을 여기 한 곳에 두고 필요한 것만 덮어쓴다.
"""


def signup_body(username: str, password: str = "pw123456", **overrides) -> dict:
    """가입 요청 본문. 검증하려는 항목만 overrides로 바꿔 쓴다."""
    body = {
        "username": username,
        "password": password,
        "name": "테스트사용자",
        "phone": "010-0000-0000",
        # 이메일은 계정마다 달라야 한다(UNIQUE). 아이디에서 만들어 충돌을 피한다.
        "email": f"{username}@example.com",
        "gender": "여성",
        "age_group": "20대",
        "consents": {"terms_of_service": True, "privacy": True, "marketing": False},
    }
    body.update(overrides)
    return body
