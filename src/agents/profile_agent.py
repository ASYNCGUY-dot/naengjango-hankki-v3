"""
Profile Agent - 1단계
- 역할: 사용자가 입력한 프로필 정보를 검증하고 users 테이블에 구조화해서 저장한다.
- 아직 Streamlit 연결 전이라, 프로필은 하드코딩된 딕셔너리로 테스트한다.
"""

import sqlite3

DB_PATH = "data/app.db"

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


def save_user_profile(cur, profile: dict) -> int:
    """검증된 프로필을 users 테이블에 저장하고 새로 생긴 user_id를 반환한다."""
    cur.execute("""
        INSERT INTO users (gender, age_group, allergy, health_goal, purpose,
                            cooking_level, supplements, household_size, novelty_pref, cooking_tools,
                            medical_conditions)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        profile["gender"],
        profile["age_group"],
        profile["allergy"],          # 예: "새우,땅콩" 처럼 콤마로 구분된 문자열
        profile["health_goal"],
        profile["purpose"],
        profile["cooking_level"],
        profile["supplements"],
        profile["household_size"],
        profile["novelty_pref"],
        profile["cooking_tools"],    # 예: "가스레인지,전자레인지" 처럼 콤마로 구분된 문자열
        profile.get("medical_conditions", ""),  # 예: "고혈압,당뇨" (없으면 빈 문자열)
    ))
    return cur.lastrowid


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

    missing = validate_profile(test_profile)
    if missing:
        print(f"프로필에 필수 항목이 빠졌습니다: {missing}")
    else:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        user_id = save_user_profile(cur, test_profile)
        conn.commit()
        conn.close()
        print(f"프로필 저장 완료. user_id = {user_id}")
        print(test_profile)
