"""
Brag Agent - 자랑하기 (2026-08-20)

이 서비스로 만들어본 결과를 사진과 함께 올리고, 서로 좋아요를 누른다.

핵심 규칙 하나만 기억하면 된다. **자랑 글의 좋아요는 그 글이 고른 레시피의 추천에도
반영되지만, 사람당 레시피당 1회다.** 같은 레시피로 쓴 글이 여럿이고 한 사람이 전부
좋아요를 눌러도 레시피 추천은 하나만 오른다 - 유저 등록 레시피의 공개 기준이 추천
3회인데(recommendation_agent.USER_RECIPE_MIN_LIKES) 그 기준이 한 사람에게 휘둘리면
안 되기 때문이다.

그래서 자랑 글 좋아요를 뗄 때 레시피 추천을 같이 떼면 안 된다. 그 사람이 같은
레시피의 다른 글에 아직 좋아요를 눌러 두었을 수 있다. 남은 것이 하나도 없을 때만 뗀다.
"""

from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_brag(cur, user_id: int, recipe_id: int, body: str, image_url: str | None) -> int:
    cur.execute(
        "INSERT INTO brags (user_id, recipe_id, image_url, body, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (user_id, recipe_id, image_url, body.strip(), _now()),
    )
    return cur.lastrowid


def list_brags(cur, viewer_id: int | None, limit: int = 20, offset: int = 0) -> list[dict]:
    """최신순 피드. viewer_id가 있으면 "내가 좋아요를 눌렀는가"를 함께 준다.

    비로그인도 읽을 수 있다(viewer_id=None). 남의 음식 사진이 이 앱에서 가장 강한
    가입 유인이라, 로그인 벽 뒤에 두지 않는다.
    """
    cur.execute(
        """
        SELECT b.id, b.recipe_id, b.image_url, b.body, b.created_at,
               u.username, r.menu_name, r.image_url,
               (SELECT COUNT(*) FROM brag_likes l WHERE l.brag_id = b.id)
        FROM brags b
        JOIN users u ON u.id = b.user_id
        JOIN recipes r ON r.id = b.recipe_id
        ORDER BY b.created_at DESC, b.id DESC
        LIMIT ? OFFSET ?
        """,
        (limit, offset),
    )
    rows = cur.fetchall()
    if not rows:
        return []

    liked: set[int] = set()
    if viewer_id is not None:
        brag_ids = [row[0] for row in rows]
        placeholders = ",".join("?" for _ in brag_ids)
        cur.execute(
            f"SELECT brag_id FROM brag_likes WHERE user_id = ? AND brag_id IN ({placeholders})",
            [viewer_id, *brag_ids],
        )
        liked = {row[0] for row in cur.fetchall()}

    return [
        {
            "id": row[0],
            "recipe_id": row[1],
            "image_url": row[2],
            "body": row[3],
            "created_at": row[4],
            "username": row[5],
            "menu_name": row[6],
            "recipe_image_url": row[7],
            "like_count": row[8],
            "liked_by_me": row[0] in liked,
        }
        for row in rows
    ]


def delete_brag(cur, brag_id: int, user_id: int) -> bool:
    """본인 글만 지운다.

    레시피 추천은 건드리지 않는다. 글이 사라져도 "이 레시피를 좋게 봤다"는 다른
    사람들의 판단까지 되돌릴 이유가 없다.
    """
    cur.execute("SELECT id FROM brags WHERE id = ? AND user_id = ?", (brag_id, user_id))
    if cur.fetchone() is None:
        return False
    cur.execute("DELETE FROM brag_likes WHERE brag_id = ?", (brag_id,))
    cur.execute("DELETE FROM brags WHERE id = ?", (brag_id,))
    return True


def _recipe_of(cur, brag_id: int) -> int | None:
    cur.execute("SELECT recipe_id FROM brags WHERE id = ?", (brag_id,))
    row = cur.fetchone()
    return row[0] if row else None


def _has_other_liked_brag(cur, user_id: int, recipe_id: int, except_brag_id: int) -> bool:
    """이 사람이 같은 레시피의 다른 자랑 글에 아직 좋아요를 눌러 두었는가."""
    cur.execute(
        "SELECT 1 FROM brag_likes l JOIN brags b ON b.id = l.brag_id "
        "WHERE l.user_id = ? AND b.recipe_id = ? AND l.brag_id != ? LIMIT 1",
        (user_id, recipe_id, except_brag_id),
    )
    return cur.fetchone() is not None


def toggle_brag_like(cur, brag_id: int, user_id: int) -> dict | None:
    """자랑 글 좋아요를 껐다 켠다. 레시피 추천에도 사람당 1회로 반영한다.

    반환값: {"liked": bool, "like_count": int} - 없는 글이면 None
    """
    recipe_id = _recipe_of(cur, brag_id)
    if recipe_id is None:
        return None

    cur.execute(
        "SELECT id FROM brag_likes WHERE brag_id = ? AND user_id = ?", (brag_id, user_id)
    )
    existing = cur.fetchone()

    if existing:
        cur.execute("DELETE FROM brag_likes WHERE brag_id = ? AND user_id = ?", (brag_id, user_id))
        # 같은 레시피의 다른 글에 아직 좋아요가 남아 있으면 레시피 추천은 유지한다.
        if not _has_other_liked_brag(cur, user_id, recipe_id, brag_id):
            cur.execute(
                "DELETE FROM recipe_likes WHERE recipe_id = ? AND user_id = ?",
                (recipe_id, user_id),
            )
        liked = False
    else:
        cur.execute(
            "INSERT INTO brag_likes (brag_id, user_id, created_at) VALUES (?, ?, ?)",
            (brag_id, user_id, _now()),
        )
        # 레시피 상세에서 이미 추천을 눌러 뒀을 수 있다. 그때는 그대로 둔다 -
        # 사람당 레시피당 1회이므로 두 줄을 만들지 않는다.
        cur.execute(
            "SELECT id FROM recipe_likes WHERE recipe_id = ? AND user_id = ?",
            (recipe_id, user_id),
        )
        if cur.fetchone() is None:
            cur.execute(
                "INSERT INTO recipe_likes (recipe_id, user_id, created_at) VALUES (?, ?, ?)",
                (recipe_id, user_id, _now()),
            )
        liked = True

    cur.execute("SELECT COUNT(*) FROM brag_likes WHERE brag_id = ?", (brag_id,))
    return {"liked": liked, "like_count": cur.fetchone()[0]}
