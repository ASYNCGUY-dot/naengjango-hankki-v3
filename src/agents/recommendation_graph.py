"""
Recommendation Agent - 2단계 (LangGraph로 연결 + 멀티 LLM 추천 이유 생성)

LangGraph 핵심 개념 3가지만 먼저 짚고 갑니다:
1. State: 그래프 전체가 공유하는 "상태" 데이터 (여기서는 딕셔너리 형태의 TypedDict)
2. Node: 상태를 받아서 처리하고, 업데이트된 상태를 돌려주는 함수 하나하나
3. Edge: 어떤 노드 다음에 어떤 노드로 가는지 정하는 연결선 (START/END는 시작/끝 표시)

이번 그래프는 노드 2개로 아주 단순하게 구성합니다:
  START -> load_context(프로필+후보 레시피 준비) -> generate_reasoning(OpenAI/Gemini 호출) -> END
"""

import os
import sqlite3
from typing import TypedDict, Optional

from dotenv import load_dotenv
from langgraph.graph import StateGraph, START, END

from recommendation_agent import get_user_profile, get_candidate_recipes, score_by_ingredients, DB_PATH

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


# 1) State 정의: 그래프가 주고받을 데이터의 모양
class RecommendState(TypedDict):
    user_id: int
    user_ingredients: Optional[list]   # 사용자가 갖고 있는 재료 이름 리스트 (예: ["두부", "계란"])
    profile: Optional[dict]
    candidates: Optional[list]
    selected_recipe: Optional[dict]
    openai_reason: Optional[str]
    gemini_reason: Optional[str]


def build_prompt(profile: dict, recipe: dict, user_ingredients: list) -> str:
    ingredients_text = ", ".join(user_ingredients) if user_ingredients else "(입력 안 함)"
    return f"""당신은 식단 추천 전문가입니다. 아래 사용자와 레시피 정보를 보고,
이 레시피를 이 사용자에게 추천하는 이유를 3문장 이내로 설명해주세요.
보유 재료를 몇 개나 활용할 수 있는지도 언급해주세요.

[사용자 프로필]
- 건강 목표: {profile['health_goal']}
- 이용 목적: {profile['purpose']}
- 요리 수준: {profile['cooking_level']}
- 보유 조리도구: {profile.get('cooking_tools') or '입력 안 함'}
- 알레르기: {profile['allergy']}
- 보유 재료: {ingredients_text}

[추천 레시피]
- 메뉴명: {recipe['menu_name']}
- 카테고리: {recipe['category']}
- 칼로리: {recipe['calorie']}kcal
- 영양군: {recipe['nutrition_group']}
- 보유 재료 중 활용 가능한 개수: {recipe.get('ingredient_overlap', 0)}개
"""


def call_openai(prompt: str) -> str:
    from openai import OpenAI
    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model="gpt-4o-mini",   # 만약 이 모델명이 없다는 에러가 나면, OpenAI 계정 대시보드에서 사용 가능한 모델명으로 교체
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content
    except Exception as e:
        # LLM 서버 쪽 문제(과부하, 일시 장애 등)로 실패해도 전체 추천 흐름은 멈추지 않게 한다.
        if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e) or "insufficient_quota" in str(e):
            return "(OpenAI 무료/할당 사용량을 다 써서 잠시 응답할 수 없습니다. 잠시 후 다시 시도해주세요.)"
        return f"(OpenAI 응답 실패: {e})"


def call_gemini(prompt: str) -> str:
    from google import genai
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        response = client.models.generate_content(
            model="gemini-2.5-flash",   # 마찬가지로 에러 나면 Google AI Studio에서 사용 가능한 모델명으로 교체
            contents=prompt,
        )
        return response.text
    except Exception as e:
        # Gemini 무료 티어는 하루/분당 호출 횟수 제한이 있어서, 테스트를 자주 반복하면 금방 소진된다.
        # (429 RESOURCE_EXHAUSTED) 이 경우 사용자에게 원인이 분명히 보이도록 안내 문구로 바꿔준다.
        if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
            return "(Gemini 무료 사용량을 다 써서 잠시 응답할 수 없습니다. 잠시 후 다시 시도하거나, 사용량은 https://ai.dev/rate-limit 에서 확인할 수 있습니다.)"
        return f"(Gemini 응답 실패: {e})"


# 2) Node 정의: 상태를 받아서 처리하고 업데이트된 상태를 반환하는 함수들
def node_load_context(state: RecommendState) -> RecommendState:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    profile = get_user_profile(cur, state["user_id"])
    candidates = get_candidate_recipes(cur, profile) if profile else []

    user_ingredients = state.get("user_ingredients") or []
    candidates = score_by_ingredients(cur, candidates, user_ingredients)
    conn.close()

    # score_by_ingredients가 이미 0원칙(qualifies) -> 0.5원칙(category_tier) -> 0.7원칙
    # (has_protein_match) -> 1원칙(ingredient_overlap) -> 1.5원칙(matched_weight) -> 2원칙
    # (step_count) 기준으로 정렬해뒀다 (2026-07 4차 A안, 6차 B안, 7차 재료 중요도 가중치,
    # 8차 단백질 매칭 우선순위). 체중감량/다이어트가 목표일 때는, 그 기준들은 그대로 최우선으로
    # 유지하면서 완전히 동점인 후보들 사이에서만 칼로리가 낮은 순으로 한 번 더 정렬한다
    # (칼로리만 보고 재정렬하면 "보유 재료를 거의 안 쓰는데 칼로리만 낮은" 레시피나 "반찬인데
    # 칼로리가 낮은" 레시피, "단백질은 안 쓰는데 칼로리만 낮은" 레시피가 다시 위로 튀어오르는
    # 문제가 생기므로, qualifies/category_tier/has_protein_match/overlap/matched_weight/
    # step_count를 절대 놓지 않는다 - #72: category_tier를 안 넣었을 때 냉잡채(반찬, 129kcal)가
    # 토마토제철나물샐러드(반찬, 80kcal)에만 밀리고 참치두부 주먹밥 같은 메인요리보다 앞서는
    # 문제가 있었다. #76: has_protein_match를 안 넣었을 때 두부·채소만 겹치는 레시피가 실제
    # 보유 단백질(생선·육류)을 쓰는 레시피보다 계속 이기는 문제가 있었다).
    if profile and ("체중감량" in profile.get("health_goal", "") or "다이어트" in profile.get("health_goal", "")):
        candidates.sort(key=lambda c: (
            not c.get("qualifies", False), c.get("category_tier", 1), not c.get("has_protein_match", False),
            -c.get("ingredient_overlap", 0), -c.get("matched_weight", 0.0),
            c.get("step_count", 999), c["calorie"] or 0
        ))

    selected = candidates[0] if candidates else None

    return {**state, "profile": profile, "candidates": candidates, "selected_recipe": selected}


def node_generate_reasoning(state: RecommendState) -> RecommendState:
    profile = state["profile"]
    recipe = state["selected_recipe"]

    if not profile or not recipe:
        no_result = "추천할 수 있는 레시피가 없습니다."
        return {**state, "openai_reason": no_result, "gemini_reason": no_result}

    prompt = build_prompt(profile, recipe, state.get("user_ingredients") or [])
    openai_reason = call_openai(prompt)
    gemini_reason = call_gemini(prompt)

    return {**state, "openai_reason": openai_reason, "gemini_reason": gemini_reason}


# 3) Edge 연결 및 그래프 컴파일
graph_builder = StateGraph(RecommendState)
graph_builder.add_node("load_context", node_load_context)
graph_builder.add_node("generate_reasoning", node_generate_reasoning)
graph_builder.add_edge(START, "load_context")
graph_builder.add_edge("load_context", "generate_reasoning")
graph_builder.add_edge("generate_reasoning", END)

app = graph_builder.compile()


if __name__ == "__main__":
    result = app.invoke({"user_id": 2, "user_ingredients": ["두부", "양파", "표고버섯"]})

    print(f"선택된 레시피: {result['selected_recipe']}\n")
    print("--- OpenAI 추천 이유 ---")
    print(result["openai_reason"])
    print("\n--- Gemini 추천 이유 ---")
    print(result["gemini_reason"])
