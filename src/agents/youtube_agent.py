"""
YouTube Agent [확장] - 조리 영상 링크 연동
- 역할: 레시피 이름으로 YouTube Data API v3를 검색해서 관련 영상 링크를 찾는다.
- 지침 원칙: 임베드 없이 링크만 제공한다 (저작권/이용약관 이슈 최소화).
- 참고: YouTube Data API는 하루 무료 할당량(기본 10,000 유닛)이 있고, 검색 1회에 100유닛이 든다.
        그래서 매번 검색하지 않고, recipes.youtube_url 컬럼에 한 번만 저장해서 재사용한다.
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("YOUTUBE_API_KEY")


class YouTubeQuotaExceededError(Exception):
    """YouTube Data API가 할당량 초과(429/403, quotaExceeded 등) 또는 그 외 에러 응답을 준 경우."""


def search_youtube_video(query: str) -> str | None:
    """검색어로 유튜브 영상을 찾아 첫 번째 결과의 URL을 반환한다.
    검색 결과가 없으면 None. 할당량 초과 등 API 에러 응답이면 YouTubeQuotaExceededError를 던진다
    (호출부가 '결과 없음'과 '더 이상 시도해도 소용없음'을 구분할 수 있도록)."""
    if not API_KEY:
        return None

    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet",
        "q": query,
        "type": "video",
        "maxResults": 1,
        "key": API_KEY,
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
    except Exception as e:
        print(f"(경고) 유튜브 검색 실패 ({query}): {e}")
        return None

    # HTTP 상태 코드가 200이 아니거나 응답 JSON에 "error" 키가 있으면
    # (예: 429/403 quotaExceeded, rateLimitExceeded) 정상 응답이 아니라 API 에러다.
    # 이 경우 response.json()은 예외 없이 파싱되고 "items"가 없어서, 그냥 두면
    # "검색 결과 없음"과 구분되지 않는다.
    if response.status_code != 200 or "error" in data:
        print(f"(경고) 할당량 초과 또는 API 에러 ({query}): status={response.status_code}, {data.get('error')}")
        raise YouTubeQuotaExceededError(f"status={response.status_code}: {data.get('error')}")

    items = data.get("items", [])
    if not items:
        return None
    video_id = items[0]["id"]["videoId"]
    return f"https://www.youtube.com/watch?v={video_id}"


if __name__ == "__main__":
    import sqlite3
    DB_PATH = "data/app.db"

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("SELECT id, menu_name FROM recipes WHERE youtube_url IS NULL")
    rows = cur.fetchall()
    print(f"유튜브 링크가 없는 레시피 {len(rows)}개 처리 시작")

    for recipe_id, menu_name in rows:
        url = search_youtube_video(f"{menu_name} 레시피")
        cur.execute("UPDATE recipes SET youtube_url = ? WHERE id = ?", (url, recipe_id))
        print(f"[{recipe_id}] {menu_name} -> {url}")

    conn.commit()
    conn.close()
    print("완료")
