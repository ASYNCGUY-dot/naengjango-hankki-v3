import { apiFetch, type RecipeSummary } from './client'
import type { components } from './schema'

export type { RecipeSummary }
export type CategoryCount = components['schemas']['CategoryCount']

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
