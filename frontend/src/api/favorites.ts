import { apiFetch } from './client'
import type { components } from './schema'

export type FavoriteItem = components['schemas']['FavoriteItem']

/**
 * 즐겨찾기 목록. 최신순으로 온다.
 *
 * 이 기능이 꺼져 있던 동안(2026-08-18까지) 마음에 든 레시피를 다시 찾으려면 검색밖에
 * 없었다. 재방문율이 Phase 4의 핵심 지표인데 다시 올 이유 하나가 닫혀 있던 셈이다.
 */
export async function listFavorites(
  userId: number,
  signal?: AbortSignal,
): Promise<FavoriteItem[]> {
  return apiFetch<FavoriteItem[]>(`/favorites/${userId}`, { signal })
}

/** 껐다 켰다 한 번에 처리한다. 결과로 지금 상태(favorited)를 돌려준다. */
export async function toggleFavorite(userId: number, recipeId: number): Promise<boolean> {
  const res = await apiFetch<components['schemas']['ToggleResponse']>(
    `/favorites/${userId}/${recipeId}/toggle`,
    { method: 'POST' },
  )
  return res.favorited
}
