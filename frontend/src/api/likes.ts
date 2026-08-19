import { apiFetch } from './client'
import type { components } from './schema'

export type LikeStatus = components['schemas']['LikeStatus']
export type PopularRecipeItem = components['schemas']['PopularRecipeItem']

/**
 * 추천하기 - 즐겨찾기와 다른 기능이다.
 *
 * 추천은 다른 사람에게 보이는 공개 지표다. 이 수가 쌓이면 유저가 등록한 레시피가
 * 다른 사람의 추천 후보로 올라가고(recommendation_agent.USER_RECIPE_MIN_LIKES),
 * 홈의 "많이 추천한 메뉴" 줄에도 반영된다.
 *
 * 즐겨찾기(api/favorites.ts)는 반대로 나만 보는 목록이다. 서버에서도 테이블이
 * 갈라져 있다(recipe_likes vs favorites). 화면에서 둘을 섞어 부르면 사용자는
 * 즐겨찾기를 눌러놓고 남을 도왔다고 오해한다.
 */
export async function getLikeStatus(
  recipeId: number,
  userId: number,
  signal?: AbortSignal,
): Promise<LikeStatus> {
  return apiFetch<LikeStatus>(`/recommendation/recipes/${recipeId}/like`, {
    query: { user_id: userId },
    signal,
  })
}

/** 껐다 켰다 한 번에 처리하고, 바뀐 상태와 누적 수를 함께 돌려준다. */
export async function toggleLike(recipeId: number, userId: number): Promise<LikeStatus> {
  return apiFetch<LikeStatus>(`/recommendation/recipes/${recipeId}/like/toggle`, {
    method: 'POST',
    query: { user_id: userId },
  })
}

/**
 * 많이 추천한 메뉴. 추천이 하나도 없는 레시피는 서버가 아예 빼고 준다(INNER JOIN).
 * 그래서 아무도 추천하지 않은 동안에는 빈 배열이 오고, 화면은 그 줄을 감춘다.
 */
export async function listPopularRecipes(
  limit = 10,
  signal?: AbortSignal,
): Promise<PopularRecipeItem[]> {
  return apiFetch<PopularRecipeItem[]>('/recommendation/recipes/popular', {
    query: { limit },
    signal,
  })
}
