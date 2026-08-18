import { apiFetch, type RecipeSummary } from './client'
import type { components } from './schema'

export type { RecipeSummary }
export type CategoryCount = components['schemas']['CategoryCount']
export type RecipeTheme = components['schemas']['RecipeTheme']

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
