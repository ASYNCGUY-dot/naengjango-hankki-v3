"""
Popular Recipe Agent [확장] - 홈 화면 "인기 레시피 찾아보기" 섹션 (#78)
- 역할: YouTube Data API로 카테고리별(쉐프/연예인/자취요리 등) 인기 요리 영상을 검색해서
  popular_videos 테이블에 캐싱해두고, 앱 화면은 이 캐시만 읽어서 보여준다.
- 지침 원칙: 임베드 없이 링크만 제공한다 (저작권/이용약관 이슈 최소화 - youtube_agent.py와 동일 원칙).
- 쿼터 절약: search.list는 검색 1회에 100유닛이 든다(하루 무료 할당량 10,000유닛). 그래서 앱이
  화면을 그릴 때마다 실시간 검색하지 않고, 이 파일을 "가끔"(예: 며칠에 한 번) 터미널에서 직접
  실행해서 캐시(popular_videos 테이블)만 갱신하는 방식으로 만들었다. 실제 조회수 숫자는
  videos.list(1유닛, 훨씬 저렴함)로 따로 가져온다.
"""

import os
import sqlite3
from datetime import datetime

import requests
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("YOUTUBE_API_KEY")
DB_PATH = "data/app.db"

# 카테고리명 -> 실제 검색어. 완벽한 목록일 필요는 없다(지침 8번 원칙과 같은 이유) - 유저가 자주
# 찾는 인기 카테고리 몇 개만 우선 다룬다. 필요하면 나중에 항목을 추가/수정하면 된다.
CATEGORY_QUERIES: dict[str, str] = {
    "쉐프 레시피": "백종원 이연복 쉐프 레시피",
    "연예인 레시피": "연예인 집밥 레시피",
    "자취요리": "자취요리 초간단 레시피",
    "다이어트 식단": "다이어트 식단 레시피",
    "에어프라이어 요리": "에어프라이어 요리 레시피",
}


def _get_view_counts(video_ids: list[str]) -> dict[str, int]:
    """videos.list는 search.list보다 훨씬 저렴하다(1유닛) - 실제 조회수 숫자를 보여주려고 따로 조회한다."""
    if not video_ids or not API_KEY:
        return {}

    url = "https://www.googleapis.com/youtube/v3/videos"
    params = {"part": "statistics", "id": ",".join(video_ids), "key": API_KEY}
    try:
        response = requests.get(url, params=params, timeout=10)
        items = response.json().get("items", [])
    except Exception as e:
        print(f"(경고) 조회수 확인 실패: {e}")
        return {}

    return {item["id"]: int(item.get("statistics", {}).get("viewCount", 0)) for item in items}


def _search_videos(query: str, max_results: int = 5) -> list[dict]:
    """검색어로 조회수 높은 순 영상을 찾는다 (썸네일/제목/채널명 포함). 실패하면 빈 리스트."""
    if not API_KEY:
        return []

    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet",
        "q": query,
        "type": "video",
        "order": "viewCount",         # 조회수 높은 순으로 정렬해서 검색
        "regionCode": "KR",
        "relevanceLanguage": "ko",
        "maxResults": max_results,
        "key": API_KEY,
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        items = response.json().get("items", [])
    except Exception as e:
        print(f"(경고) 유튜브 검색 실패 ({query}): {e}")
        return []

    video_ids = [item["id"]["videoId"] for item in items if item.get("id", {}).get("videoId")]
    view_counts = _get_view_counts(video_ids)

    videos = []
    for item in items:
        video_id = item.get("id", {}).get("videoId")
        if not video_id:
            continue
        snippet = item.get("snippet", {})
        videos.append({
            "video_id": video_id,
            "video_title": snippet.get("title", ""),
            "channel_title": snippet.get("channelTitle", ""),
            "thumbnail_url": snippet.get("thumbnails", {}).get("medium", {}).get("url", ""),
            "video_url": f"https://www.youtube.com/watch?v={video_id}",
            "view_count": view_counts.get(video_id, 0),
        })
    return videos


def refresh_popular_videos(cur, category: str, query: str, max_results: int = 5) -> int:
    """이 카테고리의 캐시를 지우고 새로 검색한 결과로 채운다. 반환값: 저장한 영상 개수."""
    videos = _search_videos(query, max_results)
    if not videos:
        return 0

    cur.execute("DELETE FROM popular_videos WHERE category = ?", (category,))
    now = datetime.now().isoformat()
    for v in videos:
        cur.execute(
            """
            INSERT INTO popular_videos
                (category, video_title, channel_title, video_id, thumbnail_url, video_url, view_count, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (category, v["video_title"], v["channel_title"], v["video_id"],
             v["thumbnail_url"], v["video_url"], v["view_count"], now),
        )
    return len(videos)


def get_popular_video_categories(cur) -> list[str]:
    """캐시에 실제로 데이터가 있는 카테고리만 반환한다 (아직 한 번도 못 가져온 카테고리는 화면에서 숨김)."""
    cur.execute("SELECT DISTINCT category FROM popular_videos ORDER BY category")
    return [row[0] for row in cur.fetchall()]


def get_cached_popular_videos(cur, category: str, limit: int = 5) -> list[dict]:
    """캐시 테이블에서 이 카테고리의 영상을 조회수 높은 순으로 가져온다 (실시간 API 호출 없음)."""
    cur.execute(
        """
        SELECT video_title, channel_title, video_id, thumbnail_url, video_url, view_count, fetched_at
        FROM popular_videos WHERE category = ? ORDER BY view_count DESC LIMIT ?
        """,
        (category, limit),
    )
    columns = ["video_title", "channel_title", "video_id", "thumbnail_url", "video_url", "view_count", "fetched_at"]
    return [dict(zip(columns, row)) for row in cur.fetchall()]


if __name__ == "__main__":
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    if not API_KEY:
        print("(경고) .env에 YOUTUBE_API_KEY가 없어서 실행할 수 없습니다.")
    else:
        for category, query in CATEGORY_QUERIES.items():
            count = refresh_popular_videos(cur, category, query)
            print(f"[{category}] '{query}' 검색 -> {count}개 저장")
        conn.commit()

    conn.close()
    print("완료. 이 스크립트는 며칠에 한 번씩만 다시 실행해도 충분합니다 (유튜브 API 하루 할당량 절약).")
