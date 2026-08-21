"""
Feedback Agent - 앱에 대한 피드백 (2026-08-22)

Phase 4에서 "어디서 멈추는가"는 usage_events가 알려주지만 **왜** 멈췄는지는
사람이 적어줘야만 안다. 그걸 앱 안에서 받는다.

읽는 범위가 둘로 나뉜다. 쓴 사람은 자기 글만, 관리자는 전부 본다. 사용자
테스트에서 남의 의견이 보이면 그쪽으로 끌려가서, 두 번째 사람부터는 자기 생각이
아니라 "나도 그랬어"를 쓰게 된다.
"""

from datetime import datetime, timezone


def create_feedback(cur, user_id: int, body: str) -> int:
    cur.execute(
        "INSERT INTO feedback (user_id, body, created_at) VALUES (?, ?, ?)",
        (user_id, body.strip(), datetime.now(timezone.utc).isoformat()),
    )
    return cur.lastrowid


def list_my_feedback(cur, user_id: int) -> list[dict]:
    """내가 쓴 것만. 최신순."""
    cur.execute(
        "SELECT id, body, created_at FROM feedback WHERE user_id = ? "
        "ORDER BY created_at DESC, id DESC",
        (user_id,),
    )
    return [{"id": r[0], "body": r[1], "created_at": r[2], "username": None} for r in cur.fetchall()]


def list_all_feedback(cur, limit: int = 200) -> list[dict]:
    """관리자용. 누가 썼는지 함께 준다 - 그 사람의 사용 기록과 맞춰 봐야 한다."""
    cur.execute(
        "SELECT f.id, f.body, f.created_at, u.username "
        "FROM feedback f JOIN users u ON u.id = f.user_id "
        "ORDER BY f.created_at DESC, f.id DESC LIMIT ?",
        (limit,),
    )
    return [
        {"id": r[0], "body": r[1], "created_at": r[2], "username": r[3]} for r in cur.fetchall()
    ]


def delete_my_feedback(cur, feedback_id: int, user_id: int) -> bool:
    """쓴 사람만 지운다. 관리자도 남의 글은 못 지운다 - 읽으려고 있는 것이지
    치우려고 있는 것이 아니다."""
    cur.execute("SELECT id FROM feedback WHERE id = ? AND user_id = ?", (feedback_id, user_id))
    if cur.fetchone() is None:
        return False
    cur.execute("DELETE FROM feedback WHERE id = ?", (feedback_id,))
    return True
