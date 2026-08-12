"""
Profile Agent - 1단계
- 역할: 사용자가 입력한 프로필 정보를 검증하고 users 테이블에 구조화해서 저장한다.
- 아직 Streamlit 연결 전이라, 프로필은 하드코딩된 딕셔너리로 테스트한다.
"""

# save_user_profile()을 없애면서 이 모듈은 DB에 직접 연결하지 않게 됐다
# (sqlite3 import와 DB_PATH도 그래서 함께 뺐다). 커서는 호출부에서 받는다.

# users 테이블에 실제로 있는 컬럼과 맞춰서 필수 항목을 정의
# medical_conditions(병력정보)는 선택 입력(체크 안 해도 "없음"으로 취급)이라 REQUIRED_FIELDS에는
# 안 넣었다 - 폼에서 항상 값(빈 문자열 포함)을 넘겨주므로 저장/수정 쿼리에만 포함시키면 된다.
REQUIRED_FIELDS = [
    "gender", "age_group", "allergy", "health_goal",
    "purpose", "cooking_level", "supplements",
    "household_size", "novelty_pref", "cooking_tools",
]


def validate_profile(profile: dict) -> list[str]:
    """
    필수 항목이 빠졌는지 확인한다.
    문제없으면 빈 리스트, 문제있으면 누락된 필드 이름 리스트를 반환한다.
    """
    missing = [field for field in REQUIRED_FIELDS if field not in profile]
    return missing


# save_user_profile()은 V3 Phase 1(2026-08-12)에서 없앴다. 프로필만 받아 users 행을
# 새로 만드는 함수였는데, username/password_hash 없이 행이 생기는 유일한 경로였다.
# 운영 DB에 쌓인 43개 계정 중 34개가 이 경로로 생긴 빈 행이었다. V3는 가입으로 계정을
# 먼저 만들고 그 계정에 프로필을 붙이므로(update_user_profile), 새 행을 만드는 쪽은
# auth_agent.signup() 하나로 일원화한다. 자세한 배경은
# migration/005_users_username_required.sql 참고.


def update_user_profile(cur, user_id: int, profile: dict):
    """
    로그인한 사용자용: 새 행을 추가하지 않고, 기존 계정(user_id)의 프로필 항목만 갱신한다.
    (username/password_hash는 건드리지 않는다)
    """
    cur.execute("""
        UPDATE users SET
            gender = ?, age_group = ?, allergy = ?, health_goal = ?, purpose = ?,
            cooking_level = ?, supplements = ?, household_size = ?, novelty_pref = ?,
            cooking_tools = ?, medical_conditions = ?
        WHERE id = ?
    """, (
        profile["gender"],
        profile["age_group"],
        profile["allergy"],
        profile["health_goal"],
        profile["purpose"],
        profile["cooking_level"],
        profile["supplements"],
        profile["household_size"],
        profile["novelty_pref"],
        profile["cooking_tools"],
        profile.get("medical_conditions", ""),
        user_id,
    ))


if __name__ == "__main__":
    # 테스트용 하드코딩 프로필
    test_profile = {
        "gender": "F",
        "age_group": "20대",
        "allergy": "새우,땅콩",
        "health_goal": "체중감량",
        "purpose": "자취생 식단관리",
        "cooking_level": "초급",
        "supplements": "없음",
        "household_size": 1,
        "novelty_pref": "새로운 메뉴 선호",
        "cooking_tools": "가스레인지,전자레인지",
    }

    # save_user_profile()을 없앤 뒤로 이 자기점검은 DB를 건드리지 않는다. 저장은 이미
    # 존재하는 계정을 대상으로만 하므로(update_user_profile), user_id 없이 단독 실행하는
    # 스크립트에서는 검증 부분만 확인하는 게 맞다.
    missing = validate_profile(test_profile)
    if missing:
        print(f"프로필에 필수 항목이 빠졌습니다: {missing}")
    else:
        print("프로필 검증 통과")
        print(test_profile)
