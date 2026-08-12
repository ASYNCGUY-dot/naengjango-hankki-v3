"""
Safety Agent - 1단계
- 역할 1: 회수·판매중지 정보(I0490)에서 재료명과 관련된 회수 이력이 있는지 확인
- 역할 2: 사용자가 입력한 재료의 유통기한이 임박했는지 확인
- 결과는 safety_notes 테이블에 저장한다.
"""

import os
import sqlite3
import requests
from datetime import date, datetime
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("FOODSAFETY_API_KEY")
DB_PATH = "data/app.db"


def get_all_recalls() -> list[dict]:
    """회수·판매중지 정보(I0490) 전체를 가져온다. (건수는 매일 바뀔 수 있어 매번 확인 후 가져온다)"""
    # 먼저 1건만 요청해서 total_count를 확인
    probe_url = f"http://openapi.foodsafetykorea.go.kr/api/{API_KEY}/I0490/json/1/1"
    probe = requests.get(probe_url, timeout=10).json()
    total = int(probe["I0490"]["total_count"])

    if total == 0:
        return []  # 현재 회수 이력이 0건이면 추가 요청 없이 빈 리스트 반환

    url = f"http://openapi.foodsafetykorea.go.kr/api/{API_KEY}/I0490/json/1/{total}"
    response = requests.get(url, timeout=10)
    data = response.json()
    return data["I0490"]["row"]


def check_recall(ingredient_name: str, recalls: list[dict]) -> list[dict]:
    """재료명이 제품명(PRDTNM) 또는 품목명(PRDLST_CD_NM)에 포함된 회수 이력을 찾는다."""
    matches = []
    for r in recalls:
        product_name = r.get("PRDTNM", "") or ""
        category_name = r.get("PRDLST_CD_NM", "") or ""
        if ingredient_name in product_name or ingredient_name in category_name:
            matches.append(r)
    return matches


def check_expiry(expiry_date_str: str, warning_days: int = 3) -> str | None:
    """
    유통기한(YYYY-MM-DD 형식 가정)이 오늘 기준 며칠 남았는지 확인.
    이미 지났으면 "만료", warning_days 이내면 "임박", 아니면 None(문제 없음) 반환.
    """
    try:
        expiry = datetime.strptime(expiry_date_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return "날짜형식오류"

    days_left = (expiry - date.today()).days
    if days_left < 0:
        return f"만료됨 ({-days_left}일 지남)"
    elif days_left <= warning_days:
        return f"임박 (D-{days_left})"
    return None


def save_safety_note(cur, ingredient_name: str, notice_text: str, source_url: str = ""):
    cur.execute(
        "INSERT INTO safety_notes (ingredient_name, notice_text, source_url, created_at) VALUES (?, ?, ?, ?)",
        (ingredient_name, notice_text, source_url, datetime.now().isoformat())
    )


if __name__ == "__main__":
    # 테스트용 하드코딩: (재료명, 유통기한)
    test_ingredients = [
        ("두부", "2026-07-08"),   # 임박 예시 (오늘 기준 며칠 안 남음)
        ("계란", "2026-06-01"),   # 이미 지난 예시
        ("콩나물", "2026-08-01"), # 여유 있는 예시
    ]

    print("회수정보 전체를 불러오는 중...")
    recalls = get_all_recalls()
    print(f"총 {len(recalls)}건의 회수정보 로드 완료.\n")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    for name, expiry in test_ingredients:
        print(f"[{name}]")

        # 1) 회수 이력 확인
        recall_matches = check_recall(name, recalls)
        if recall_matches:
            for m in recall_matches:
                notice = f"회수 이력 발견: {m.get('PRDTNM')} - 사유: {m.get('RTRVLPRVNS')}"
                print(f"   (경고) {notice}")
                save_safety_note(cur, name, notice, "foodsafetykorea.go.kr")
        else:
            print("   회수 이력 없음")

        # 2) 유통기한 확인
        expiry_status = check_expiry(expiry)
        if expiry_status:
            notice = f"유통기한 {expiry_status} (입력값: {expiry})"
            print(f"   (경고) {notice}")
            save_safety_note(cur, name, notice, "")
        else:
            print(f"   유통기한 여유 있음 (입력값: {expiry})")
        print()

    conn.commit()
    conn.close()
    print("저장 완료: data/app.db (safety_notes 테이블)")
