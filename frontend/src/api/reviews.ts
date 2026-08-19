import { apiFetch } from './client'
import type { components } from './schema'

export type ReviewItem = components['schemas']['ReviewItem']

/** 후기는 로그인 없이도 읽을 수 있다. 레시피 상세가 공유 가능한 주소이기 때문이다. */
export async function listReviews(recipeId: number, signal?: AbortSignal): Promise<ReviewItem[]> {
  return apiFetch<ReviewItem[]>(`/reviews/${recipeId}`, { signal })
}

/** 별점은 1~5. 서버가 범위를 강제하므로 화면도 그 범위만 고르게 한다. */
export async function createReview(
  recipeId: number,
  userId: number,
  rating: number,
  reviewText: string,
): Promise<void> {
  await apiFetch(`/reviews/${recipeId}`, {
    method: 'POST',
    body: { user_id: userId, rating, review_text: reviewText },
  })
}
