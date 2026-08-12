"""
V1의 safety_agent.py 로직을 HTTP 엔드포인트로 감싸는 얇은 래퍼.

2026-07-18 전체 화면 재검증 중 발견: 식약처 공공 API(openapi.foodsafetykorea.go.kr)가
가끔 응답을 아예 안 주는데(TCP 연결은 되지만 HTTP 응답이 없음), safety_agent.py는
그 경우를 잡지 않아서 requests.exceptions.RequestException이 그대로 터져 사용자에게는
설명 없는 500만 보였다. agent 파일은 그대로 두고, 이 라우터 계층에서만 예외를 잡아
"외부 서비스 응답 지연" 같은 명확한 메시지의 503으로 바꾼다.

2026-07-19 추가: 503 처리만으로는 "에러가 안 보이게" 될 뿐, 매 요청마다 여전히 식약처
API를 호출하고 그때마다 실패할 수 있다. get_all_recalls() 결과를 TTLCache로 10분간
재사용해서 (1) 호출 빈도 자체를 줄이고 (2) 방금 실패해도 직전 성공 응답이 있으면 그걸
그대로 돌려줘서 일시적 장애를 사용자가 못 느끼게 한다(api/ttl_cache.py 참고).
"""

import sqlite3

import requests
from fastapi import APIRouter, Depends, HTTPException

from pydantic import BaseModel

from api.auth_token import get_current_user_id, require_self
from api.deps import get_db
from api.ttl_cache import TTLCache
from src.agents import pantry_agent, safety_agent

router = APIRouter(prefix="/safety", tags=["safety"])

_recalls_cache = TTLCache(ttl_seconds=600)


class SafetyCheckRequest(BaseModel):
    ingredient_name: str
    expiry_date: str | None = None


class SafetyCheckResponse(BaseModel):
    recall_matches: list[dict]
    expiry_status: str | None
    saved_notes: int


@router.post("/check", response_model=SafetyCheckResponse)
def check_safety(body: SafetyCheckRequest, cur: sqlite3.Cursor = Depends(get_db)):
    try:
        recalls = _recalls_cache.get_or_fetch(safety_agent.get_all_recalls)
    except requests.RequestException:
        raise HTTPException(
            status_code=503,
            detail="식약처 회수정보 서비스가 응답하지 않습니다. 잠시 후 다시 시도해주세요.",
        )
    recall_matches = safety_agent.check_recall(body.ingredient_name, recalls)

    saved = 0
    for m in recall_matches:
        notice = f"회수 이력 발견: {m.get('PRDTNM')} - 사유: {m.get('RTRVLPRVNS')}"
        safety_agent.save_safety_note(cur, body.ingredient_name, notice, "foodsafetykorea.go.kr")
        saved += 1

    expiry_status = None
    if body.expiry_date:
        expiry_status = safety_agent.check_expiry(body.expiry_date)
        if expiry_status:
            notice = f"유통기한 {expiry_status} (입력값: {body.expiry_date})"
            safety_agent.save_safety_note(cur, body.ingredient_name, notice, "")
            saved += 1

    return SafetyCheckResponse(
        recall_matches=recall_matches,
        expiry_status=expiry_status,
        saved_notes=saved,
    )


class IngredientSafetyStatus(BaseModel):
    name: str
    expiry_date: str | None
    status: str  # "주의" 또는 "정상"
    recall_summary: str  # 회수 이력을 미리 합쳐둔 문자열(없으면 "") - 프론트엔드 중첩 목록 제약 회피
    expiry_status: str | None


class SafetyOverviewResponse(BaseModel):
    total: int
    warning_count: int
    normal_count: int
    items: list[IngredientSafetyStatus]


@router.get("/overview", response_model=SafetyOverviewResponse)
def safety_overview(
    user_id: int,
    cur: sqlite3.Cursor = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    """보유 재료 전체를 한 번에 훑어서 전체/주의/정상으로 집계한다.
    get_all_recalls()는 재료 개수와 무관하게 1번만 호출한다(N+1 방지)."""
    require_self(user_id, current_user_id)
    pantry_items = pantry_agent.get_pantry_ingredients(cur, user_id)
    if not pantry_items:
        return SafetyOverviewResponse(total=0, warning_count=0, normal_count=0, items=[])

    try:
        recalls = _recalls_cache.get_or_fetch(safety_agent.get_all_recalls)
    except requests.RequestException:
        raise HTTPException(
            status_code=503,
            detail="식약처 회수정보 서비스가 응답하지 않습니다. 잠시 후 다시 시도해주세요.",
        )

    items = []
    warning_count = 0
    for p in pantry_items:
        name = p["name"]
        expiry_date = p.get("expiry_date")
        recall_matches = safety_agent.check_recall(name, recalls)
        expiry_status = safety_agent.check_expiry(expiry_date) if expiry_date else None
        is_warning = bool(recall_matches) or bool(expiry_status)
        if is_warning:
            warning_count += 1
        notices = [f"{m.get('PRDTNM')}: {m.get('RTRVLPRVNS')}" for m in recall_matches]
        items.append(IngredientSafetyStatus(
            name=name, expiry_date=expiry_date,
            status="주의" if is_warning else "정상",
            recall_summary="; ".join(notices),
            expiry_status=expiry_status,
        ))

    return SafetyOverviewResponse(
        total=len(items),
        warning_count=warning_count,
        normal_count=len(items) - warning_count,
        items=items,
    )
