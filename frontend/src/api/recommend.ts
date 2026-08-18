import { apiFetch } from './client'
import type { components } from './schema'

export type RecommendationItem = components['schemas']['RecommendationItem']

/** 한 화면에 보여줄 개수. 2열 격자라 짝수로 둔다. */
export const RECOMMEND_LIMIT = 10

/**
 * 보유 재료로 추천을 받는다.
 *
 * 서버가 냉장고를 스스로 읽지 않는다 - 재료 이름을 쿼리로 받는다. 그래서 화면이 먼저
 * 냉장고를 조회한 뒤 그 이름들을 넘겨야 한다. 로그인 없이 체험하는 경로(/recommendation/demo)와
 * 계약을 맞추려고 이렇게 돼 있다.
 */
export async function getRecommendations(
  userId: number,
  ingredients: string[],
  signal?: AbortSignal,
): Promise<RecommendationItem[]> {
  return apiFetch<RecommendationItem[]>(`/recommendation/${userId}`, {
    query: { ingredients, limit: RECOMMEND_LIMIT },
    signal,
  })
}

export type MatchLevel = 'good' | 'weak' | 'poor'

/**
 * 이 추천이 보유 재료를 얼마나 쓰는지 한 단어로 요약한다.
 *
 * qualifies는 서버가 계산한 "자격" 판정이다. 겹치는 재료가 너무 적거나 메뉴명에 박힌
 * 핵심 재료가 없으면 false가 되고, 그런 항목은 목록 뒤로 밀린다. 화면에서도 구분해줘야
 * 사용자가 "왜 이게 추천됐지"라고 느끼지 않는다.
 */
export function matchLevel(item: RecommendationItem): MatchLevel {
  if (!item.qualifies) return 'poor'
  return item.ingredient_overlap >= 2 ? 'good' : 'weak'
}

export function describeMatch(item: RecommendationItem): string {
  if (item.ingredient_overlap === 0) return '가진 재료 없이 만드는 메뉴'
  return `재료 ${item.ingredient_overlap}개 활용`
}

/**
 * "지금 만들 수 있나"에 답하는 한 줄.
 *
 * 겹치는 재료 개수만 보여주면 "그래서 오늘 되는 거야?"에 답하지 못한다. 서버가 이미
 * 세고 있던 값인데 응답에서 버려지고 있었다(2026-08-18까지).
 *
 * null을 돌려주면 화면이 아무것도 안 그린다 - 재료를 안 보고 고른 추천(대체 메뉴)은
 * missing_count가 0으로 오는데, 그건 "다 있다"가 아니라 "안 셌다"는 뜻이라 "지금 바로
 * 만들 수 있어요"라고 말하면 거짓이 된다.
 */
export function describeMissing(item: RecommendationItem): string | null {
  if (item.ingredient_overlap === 0) return null
  if (item.missing_count === 0) return '지금 바로 만들 수 있어요'
  return `${item.missing_count}개만 더 있으면 돼요`
}
