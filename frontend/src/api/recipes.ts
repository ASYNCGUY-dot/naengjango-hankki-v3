import { apiFetch, type RecipeSummary } from './client'
import type { components } from './schema'

export type { RecipeSummary }
export type CategoryCount = components['schemas']['CategoryCount']
export type RecipeTheme = components['schemas']['RecipeTheme']
export type NutritionFit = components['schemas']['NutritionFitResponse']
export type Substitution = components['schemas']['SubstitutionResponse']

/**
 * 냉장고에 없는 재료와, 대신 쓸 수 있는 것.
 *
 * 커버리지와 목록은 같은 기준으로 계산된다 - "7개 부족"이라고 적어놓고 목록에 5개만
 * 나오면 둘 다 못 믿게 된다(substitution_agent가 지키는 불변조건).
 *
 * 냉장고에 저장된 재료를 기준으로 한다. 추천 화면에서 그때그때 고친 재료가 아니라는
 * 뜻이라, 상세 화면은 "냉장고 기준"이라고 밝힌다.
 */
export async function getSubstitution(
  recipeId: number,
  userId: number,
  signal?: AbortSignal,
): Promise<Substitution> {
  return apiFetch<Substitution>(`/recommendation/recipes/${recipeId}/substitution`, {
    query: { user_id: userId },
    signal,
  })
}

/**
 * 이 레시피가 나에게 어떤 영양소를 얼마나 채워주는지.
 *
 * 온보딩에서 받은 성별·연령대로 공식 권장섭취량을 찾고, 복용 중인 영양제와 병력을
 * 반영한다(2025 한국인 영양소 섭취기준). 그 질문들이 실제로 쓰이는 유일한 자리다.
 *
 * 성별·연령대를 안 밝히면 서버가 `available: false`로 답한다 - 오류가 아니라
 * "기준을 정할 수 없다"는 뜻이므로 화면이 그렇게 안내해야 한다.
 */
export async function getNutritionFit(
  recipeId: number,
  userId: number,
  signal?: AbortSignal,
): Promise<NutritionFit> {
  return apiFetch<NutritionFit>(`/recommendation/recipes/${recipeId}/nutrition-fit`, {
    query: { user_id: userId },
    signal,
  })
}

/** 화면의 "전체" 칩. 서버에 이 값을 보내면 필터를 걸지 않는다(search_all_recipes 참고). */
export const ALL_CATEGORIES = '전체'

/** 한 번에 가져올 개수. 2열 격자라 짝수로 둔다. */
export const PAGE_SIZE = 20

export async function searchRecipes(options: {
  keyword?: string
  category?: string
  offset?: number
  signal?: AbortSignal
}): Promise<RecipeSummary[]> {
  const { keyword = '', category, offset = 0, signal } = options
  return apiFetch<RecipeSummary[]>('/recommendation/recipes/search', {
    query: {
      keyword,
      // "전체"는 필터 없음이라 아예 보내지 않는다.
      category: category && category !== ALL_CATEGORIES ? category : undefined,
      limit: PAGE_SIZE,
      offset,
    },
    signal,
  })
}

export async function listCategories(signal?: AbortSignal): Promise<CategoryCount[]> {
  return apiFetch<CategoryCount[]>('/recommendation/recipes/categories', { signal })
}

/** 한 테마 줄에 보여줄 개수. 가로로 넘기는 줄이라 화면 폭과 무관하게 정한다. */
export const THEME_SIZE = 10

/**
 * 홈 화면 테마들. 네 줄이 한 번의 요청으로 온다.
 *
 * 줄마다 따로 부르면 무료 티어(0.1 CPU)에서 왕복이 네 배가 되고, 콜드스타트까지 겹치면
 * 첫 화면이 그만큼 늦어진다.
 */
export async function listThemes(signal?: AbortSignal): Promise<RecipeTheme[]> {
  return apiFetch<RecipeTheme[]>('/recommendation/recipes/themes', {
    query: { limit: THEME_SIZE },
    signal,
  })
}
