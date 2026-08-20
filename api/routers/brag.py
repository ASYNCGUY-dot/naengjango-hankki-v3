"""
자랑하기 - 만들어본 결과를 올리고 서로 좋아요를 누른다 (2026-08-20).

피드 읽기는 인가를 요구하지 않는다. 남의 음식 사진이 이 앱에서 가장 강한 가입
유인이라, 로그인 벽 뒤에 두지 않는다(레시피 상세와 같은 방침).

사진은 이 라우터가 받지 않는다. 별도의 업로드 엔드포인트가 Supabase Storage에 올리고
공개 주소를 돌려주면, 그 주소를 image_url로 함께 보낸다.
"""

import sqlite3

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from pydantic import BaseModel, Field

from api import usage_log
from api.auth_token import get_current_user_id, get_optional_user_id, require_self
from api.deps import get_db
from src.agents import brag_agent, storage_agent

router = APIRouter(prefix="/brags", tags=["brags"])


class BragRequest(BaseModel):
    recipe_id: int
    # 화면에도 maxLength가 있지만 그건 편의일 뿐이다. 공개 콘텐츠라 서버가 다시 건다.
    body: str = Field(min_length=1, max_length=1000)
    image_url: str | None = Field(default=None, max_length=500)


class BragItem(BaseModel):
    id: int
    recipe_id: int
    image_url: str | None
    body: str
    created_at: str
    username: str
    menu_name: str
    recipe_image_url: str | None
    like_count: int
    liked_by_me: bool


class BragLikeStatus(BaseModel):
    liked: bool
    like_count: int


class UploadResponse(BaseModel):
    image_url: str


@router.post("/photo", response_model=UploadResponse)
async def upload_photo(
    user_id: int,
    file: UploadFile = File(...),
    current_user_id: int = Depends(get_current_user_id),
):
    """사진 한 장을 올리고 공개 주소를 돌려준다. 글 작성과 분리돼 있다.

    나눈 이유는 두 가지다. 사진 업로드가 느린데(무료 티어) 글까지 한 요청에 묶으면
    실패했을 때 쓴 글이 통째로 날아간다. 그리고 사진을 먼저 올려두면 화면이 미리보기를
    보여줄 수 있다.
    """
    require_self(user_id, current_user_id)

    if not storage_agent.is_configured():
        raise HTTPException(status_code=503, detail="사진 저장소가 설정되지 않았습니다.")

    data = await file.read()
    if len(data) > storage_agent.MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"사진은 {storage_agent.MAX_BYTES // (1024 * 1024)}MB까지 올릴 수 있어요.",
        )
    # 확장자와 Content-Type은 둘 다 위조할 수 있다. 실제 바이트로 판별한다.
    if storage_agent.detect_image(data) is None:
        raise HTTPException(status_code=415, detail="JPEG·PNG·WebP 사진만 올릴 수 있어요.")

    image_url = storage_agent.upload_image(data, user_id)
    if image_url is None:
        raise HTTPException(status_code=502, detail="사진을 올리지 못했습니다. 잠시 후 다시 시도해주세요.")
    return UploadResponse(image_url=image_url)


@router.get("", response_model=list[BragItem])
def list_brags(
    limit: int = 20,
    offset: int = 0,
    cur: sqlite3.Cursor = Depends(get_db),
    viewer_id: int | None = Depends(get_optional_user_id),
):
    # 한 번에 너무 많이 주면 무료 티어에서 느려진다. 화면은 더 보기로 이어 받는다.
    return brag_agent.list_brags(cur, viewer_id, limit=min(limit, 50), offset=max(offset, 0))


@router.post("", response_model=BragItem)
def create_brag(
    user_id: int,
    body: BragRequest,
    cur: sqlite3.Cursor = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    require_self(user_id, current_user_id)
    cur.execute("SELECT id FROM recipes WHERE id = ?", (body.recipe_id,))
    if cur.fetchone() is None:
        raise HTTPException(status_code=404, detail="존재하지 않는 recipe_id입니다.")

    brag_id = brag_agent.create_brag(cur, user_id, body.recipe_id, body.body, body.image_url)
    usage_log.record(cur, usage_log.BRAG_POST, user_id=user_id, recipe_id=body.recipe_id)

    # 방금 만든 글 하나를 그대로 돌려준다. 화면이 목록을 다시 받지 않아도 되게.
    for item in brag_agent.list_brags(cur, user_id, limit=50):
        if item["id"] == brag_id:
            return item
    raise HTTPException(status_code=500, detail="글을 저장했지만 다시 읽지 못했습니다.")


@router.delete("/{brag_id}")
def delete_brag(
    brag_id: int,
    user_id: int,
    cur: sqlite3.Cursor = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    require_self(user_id, current_user_id)
    if not brag_agent.delete_brag(cur, brag_id, user_id):
        raise HTTPException(status_code=404, detail="본인이 쓴 글이 아니거나 존재하지 않습니다.")
    return {"deleted": True}


@router.post("/{brag_id}/like/toggle", response_model=BragLikeStatus)
def toggle_like(
    brag_id: int,
    user_id: int,
    cur: sqlite3.Cursor = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    """이 좋아요는 글이 고른 레시피의 추천에도 반영된다 - 사람당 레시피당 1회."""
    require_self(user_id, current_user_id)
    result = brag_agent.toggle_brag_like(cur, brag_id, user_id)
    if result is None:
        raise HTTPException(status_code=404, detail="존재하지 않는 글입니다.")
    return BragLikeStatus(**result)
