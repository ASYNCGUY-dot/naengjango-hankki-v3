"""
V1의 popular_recipe_agent.py 로직을 HTTP 엔드포인트로 감싸는 얇은 래퍼.
캐시 조회 함수(get_popular_video_categories, get_cached_popular_videos)만 노출한다
- 캐시 갱신(refresh_popular_videos)은 유튜브 API 할당량을 쓰므로
  scripts/refresh_popular_videos.py로 가끔 수동/예약 실행한다(agent 원본 주석과 동일한 원칙).
"""

import sqlite3

from fastapi import APIRouter, Depends

from pydantic import BaseModel

from api.deps import get_db
from src.agents import popular_recipe_agent

router = APIRouter(prefix="/popular-videos", tags=["popular-videos"])


class PopularVideo(BaseModel):
    video_title: str
    channel_title: str
    video_id: str
    thumbnail_url: str
    video_url: str
    view_count: int
    fetched_at: str


@router.get("/categories", response_model=list[str])
def list_categories(cur: sqlite3.Cursor = Depends(get_db)):
    return popular_recipe_agent.get_popular_video_categories(cur)


@router.get("/{category}", response_model=list[PopularVideo])
def get_videos(category: str, limit: int = 5, cur: sqlite3.Cursor = Depends(get_db)):
    return popular_recipe_agent.get_cached_popular_videos(cur, category, limit)
