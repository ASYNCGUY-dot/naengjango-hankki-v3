"""본인이 먹은 양과 당시 영양값을 보관하고 한국 시간의 오늘 섭취량을 계산한다.

자정에는 조회 구간만 바뀐다. 이전 기록이나 영양 스냅샷을 지우는 작업은 없다.
"""

import json
import math
import sqlite3
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from api.auth_token import get_current_user_id
from api.deps import get_db
from api.routers.nutrition import MICRO_KEYS, NutritionFitResponse
from src.agents import ingredient_catalog_agent, nutrition_target_agent, portion_agent, recommendation_agent

router = APIRouter(prefix="/meals", tags=["meals"])

# 서비스의 날짜 경계는 현재 한국 표준시(UTC+9)다. 서버의 로컬 시간대에 의존하지 않는다.
KST = timezone(timedelta(hours=9), name="Asia/Seoul")
NUTRIENT_KEYS = ["protein_g", *MICRO_KEYS, "sodium_mg"]
_ENTRY_COLUMNS = "id, recipe_id, recipe_name, servings, consumed_at"


class MealUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    servings: float = Field(ge=0.1, le=10, strict=True, allow_inf_nan=False)

    @field_validator("servings", mode="before")
    @classmethod
    def reject_nonfinite(cls, value):
        # JSON의 비표준 NaN/Infinity 입력도 422로 거절한다. 검증 오류의 input에
        # 이 값을 남기면 JSON 오류 응답을 직렬화할 때 다시 예외가 날 수 있다.
        if isinstance(value, (int, float)):
            try:
                finite = math.isfinite(value)
            except OverflowError:
                finite = False
            if not finite:
                raise HTTPException(status_code=422, detail="먹은 양은 0.1~10인분의 유한한 수여야 합니다.")
        return value


class MealCreateRequest(MealUpdateRequest):
    recipe_id: int = Field(gt=0, strict=True)
    request_id: UUID


class MealEntry(BaseModel):
    id: int
    recipe_id: int | None
    recipe_name: str
    servings: float
    consumed_at: str


class DailyNutritionResponse(BaseModel):
    date: str
    timezone: str
    server_now: str
    next_reset_at: str
    nutrition: NutritionFitResponse
    meals: list[MealEntry]
    incomplete_nutrients: list[str]


def _now() -> datetime:
    """테스트에서 교체할 수 있는 서버 시계. 항상 시간대가 있는 시각을 사용한다."""
    return datetime.now(timezone.utc)


def _utc_text(value: datetime) -> str:
    # TEXT 컬럼의 문자열 비교도 시간 순서와 같도록 UTC와 소수초 자릿수를 통일한다.
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _entry(row) -> MealEntry:
    return MealEntry(**dict(zip(("id", "recipe_id", "recipe_name", "servings", "consumed_at"), row[:5])))


def _nonnegative_number(value) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def _one_serving_micro(cur, recipe_id: int) -> tuple[dict, set[str]]:
    """가구원 수와 무관한 1인분. 누락/근사 매칭은 영양소별로 함께 기록한다."""
    base_servings, items = portion_agent.get_recipe_ingredients(cur, recipe_id)
    base = _nonnegative_number(base_servings)
    items = [item for item in items if portion_agent.classify_ingredient_row(item["name"], item["amount"]) == "ingredient"]
    if not items or not base:
        return {}, set(MICRO_KEYS)

    totals = {}
    incomplete = set()
    for item in items:
        amount = _nonnegative_number(item["amount"])
        if amount == 0:
            continue
        if recommendation_agent.is_staple(item["name"]) or amount is None or item["unit"] != "g":
            incomplete.update(MICRO_KEYS)
            continue
        matched = ingredient_catalog_agent.match_nutrition_local(cur, item["name"])
        if matched is None:
            incomplete.update(MICRO_KEYS)
            continue
        if not matched.get("is_exact_match"):
            incomplete.update(MICRO_KEYS)
        for key in MICRO_KEYS:
            value = _nonnegative_number(matched.get(key))
            if value is None:
                incomplete.add(key)
            else:
                total = _nonnegative_number(totals.get(key, 0.0) + value * (amount / base / 100))
                if total is None:
                    incomplete.add(key)
                else:
                    totals[key] = total
    incomplete.update(key for key in MICRO_KEYS if key not in totals)
    return totals, incomplete


def _snapshot(cur, recipe_id: int, raw_nutrients: str | None) -> dict:
    try:
        nutrients = json.loads(raw_nutrients) if raw_nutrients else {}
    except (ValueError, TypeError):
        nutrients = {}
    if not isinstance(nutrients, dict):
        nutrients = {}

    values, incomplete = _one_serving_micro(cur, recipe_id)
    # 기존 영양 API와 같이 recipes.nutrients_json의 macro는 1인분 기준이다.
    for key in ("protein_g", "sodium_mg"):
        value = _nonnegative_number(nutrients.get(key))
        if value is None:
            incomplete.add(key)
        else:
            values[key] = value
    return {"values": values, "incomplete_nutrients": sorted(incomplete)}


def _find_request(cur, user_id: int, request_id: UUID):
    cur.execute(
        f"SELECT {_ENTRY_COLUMNS}, request_recipe_id, request_servings, deleted_at "
        "FROM meal_logs WHERE user_id = ? AND request_id = ?",
        (user_id, str(request_id)),
    )
    return cur.fetchone()


def _replayed_entry(row, body: MealCreateRequest) -> MealEntry:
    if row[5] != body.recipe_id or row[6] != body.servings:
        raise HTTPException(status_code=409, detail="같은 요청 번호에 다른 식사 정보가 사용되었습니다.")
    if row[7] is not None:
        raise HTTPException(status_code=409, detail="이미 취소한 식사입니다. 다시 기록하려면 새로 추가해주세요.")
    return _entry(row)


@router.post("", response_model=MealEntry, status_code=201)
def create_meal(
    body: MealCreateRequest,
    cur: sqlite3.Cursor = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    previous = _find_request(cur, current_user_id, body.request_id)
    if previous is not None:
        return _replayed_entry(previous, body)

    cur.execute(
        "SELECT menu_name, nutrients_json FROM recipes "
        "WHERE id = ? AND (status = 'approved' OR submitted_by = ?)",
        (body.recipe_id, current_user_id),
    )
    recipe = cur.fetchone()
    if recipe is None:
        raise HTTPException(status_code=404, detail="기록할 수 없는 레시피입니다.")

    snapshot = _snapshot(cur, body.recipe_id, recipe[1])
    now = _utc_text(_now())
    # 동시 재시도도 한 행만 남긴다. UNIQUE 예외를 잡으면 Postgres 트랜잭션이
    # 중단되어 뒤의 SELECT/COMMIT도 실패하므로 ON CONFLICT로 처리한다.
    cur.execute(
        "INSERT INTO meal_logs (user_id, recipe_id, recipe_name, servings, consumed_at, "
        "nutrition_snapshot_json, request_id, request_recipe_id, request_servings, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT (user_id, request_id) DO NOTHING",
        (current_user_id, body.recipe_id, recipe[0] or "이름 없는 레시피", body.servings, now,
         json.dumps(snapshot, ensure_ascii=False, allow_nan=False), str(body.request_id),
         body.recipe_id, body.servings, now),
    )
    return _replayed_entry(_find_request(cur, current_user_id, body.request_id), body)


@router.get("/today", response_model=DailyNutritionResponse)
def get_today(
    cur: sqlite3.Cursor = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    now = _now().astimezone(KST)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    profile = recommendation_agent.get_user_profile(cur, current_user_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="사용자 정보를 찾을 수 없습니다.")
    cur.execute(
        f"SELECT {_ENTRY_COLUMNS}, nutrition_snapshot_json FROM meal_logs "
        "WHERE user_id = ? AND consumed_at >= ? AND consumed_at < ? AND deleted_at IS NULL "
        "ORDER BY consumed_at DESC, id DESC",
        (current_user_id, _utc_text(start), _utc_text(end)),
    )
    meals = []
    totals = dict.fromkeys(NUTRIENT_KEYS, 0.0)
    incomplete = set()
    for row in cur.fetchall():
        meals.append(_entry(row))
        snapshot = json.loads(row[5])
        for key in NUTRIENT_KEYS:
            value = snapshot["values"].get(key)
            if value is not None:
                total = _nonnegative_number(totals[key] + value * row[3])
                if total is None:
                    incomplete.add(key)
                else:
                    totals[key] = total
        incomplete.update(snapshot["incomplete_nutrients"])

    result = nutrition_target_agent.build_nutrition_fit(
        age_group=profile.get("age_group"),
        gender=profile.get("gender"),
        supplements_text=profile.get("supplements") or "",
        recipe_macro={key: totals[key] for key in ("protein_g", "sodium_mg")},
        recipe_micro={key: totals[key] for key in MICRO_KEYS},
        micro_is_partial=bool(incomplete.intersection(MICRO_KEYS)),
        medical_conditions_text=profile.get("medical_conditions") or "",
    )
    return DailyNutritionResponse(
        date=start.date().isoformat(), timezone="Asia/Seoul", server_now=now.isoformat(),
        next_reset_at=end.isoformat(), nutrition=result, meals=meals,
        incomplete_nutrients=sorted(incomplete),
    )


@router.put("/{meal_id}", response_model=MealEntry)
def update_meal(
    meal_id: int,
    body: MealUpdateRequest,
    cur: sqlite3.Cursor = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    cur.execute(
        "UPDATE meal_logs SET servings = ?, updated_at = ? "
        "WHERE id = ? AND user_id = ? AND deleted_at IS NULL "
        f"RETURNING {_ENTRY_COLUMNS}",
        (body.servings, _utc_text(_now()), meal_id, current_user_id),
    )
    row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="식사 기록을 찾을 수 없습니다.")
    return _entry(row)


@router.delete("/{meal_id}", status_code=204)
def delete_meal(
    meal_id: int,
    cur: sqlite3.Cursor = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    now = _utc_text(_now())
    cur.execute(
        "UPDATE meal_logs SET deleted_at = COALESCE(deleted_at, ?), "
        "updated_at = CASE WHEN deleted_at IS NULL THEN ? ELSE updated_at END "
        "WHERE id = ? AND user_id = ? RETURNING id",
        (now, now, meal_id, current_user_id),
    )
    if cur.fetchone() is None:
        raise HTTPException(status_code=404, detail="식사 기록을 찾을 수 없습니다.")
    return Response(status_code=204)
