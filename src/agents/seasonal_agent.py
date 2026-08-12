"""
Seasonal Agent [확장] - 제철 재료 안내
- 출처: 농림축산식품부 산하 농식품정보누리 "이달의 제철 농산물" (foodnuri.go.kr, list.do?menuNo=300106)
- 전 달(1~12월) 모두 실제 게시물을 직접 확인(web_fetch)해서 채운 값이다. 확인 시점: 2026-07-08.
  - 1~7, 11, 12월: 2026년 최신 순환 게시물 기준
  - 8~10월: 2026-07-08 시점 기준 아직 2026년 게시물이 없어(7월까지만 게시됨), 가장 최근 순환인
    2025년 게시물 기준으로 채움 (등록일 8월 2025-07-29, 9월 2025-08-26, 10월 2025-09-30)
- 참고: 월별 대표 품목 1~3개만 담은 간이 목록이다. 실제 품목은 지역·기후·연도에 따라 달라질 수 있어
        정확한 최신 정보는 농식품정보누리 사이트에서 다시 확인하는 것을 권장한다 (지침 8번 원칙과 동일).
"""

from datetime import date

SEASONAL_INGREDIENTS = {
    1: ["우엉", "딸기"],
    2: ["한라봉"],
    3: ["대파"],
    4: ["미나리"],
    5: ["오이", "토마토"],
    6: ["양배추", "애호박"],
    7: ["파프리카"],
    8: ["블루베리", "참나물"],   # foodnuri.go.kr 등록일 2025-07-29 게시물 기준
    9: ["새송이버섯", "포도"],   # foodnuri.go.kr 등록일 2025-08-26 게시물 기준
    10: ["단호박", "배"],        # foodnuri.go.kr 등록일 2025-09-30 게시물 기준
    11: ["단감", "배추"],
    12: ["연근"],
}


def get_current_season_ingredients(month: int | None = None) -> list[str]:
    month = month or date.today().month
    return SEASONAL_INGREDIENTS.get(month, [])


def find_seasonal_matches(user_ingredients: list[str], month: int | None = None) -> list[str]:
    """사용자가 입력한 재료 중 이번 달 제철 품목과 겹치는 게 있으면 반환"""
    seasonal = get_current_season_ingredients(month)
    matches = []
    for u in user_ingredients:
        u = u.strip()
        if any(u in s or s in u for s in seasonal):
            matches.append(u)
    return matches


if __name__ == "__main__":
    month = date.today().month
    print(f"이번 달({month}월) 제철 재료: {get_current_season_ingredients(month)}")
    print(find_seasonal_matches(["파프리카", "두부", "계란"], month))
