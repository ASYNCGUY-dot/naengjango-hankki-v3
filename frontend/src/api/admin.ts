import { apiFetch } from './client'
import type { components } from './schema'

export type PendingRecipe = components['schemas']['PendingRecipe']
export type PendingIngredient = components['schemas']['PendingIngredient']

/**
 * 승인 대기 큐.
 *
 * 이 화면이 없으면 등록 기능이 반쪽이다. 이름이 겹치는 레시피와 공식 DB에 이미 있는
 * 재료는 pending으로 들어가는데, 그걸 처리할 곳이 없으면 영원히 대기 상태로 남는다.
 *
 * 서버가 is_admin을 확인하므로 화면은 권한을 판단하지 않는다. 관리자가 아니면
 * 403이 오고, 그때 화면은 그냥 안내만 보여준다.
 */
export async function listPendingRecipes(
  userId: number,
  signal?: AbortSignal,
): Promise<PendingRecipe[]> {
  return apiFetch<PendingRecipe[]>('/admin/pending-recipes', {
    query: { user_id: userId },
    signal,
  })
}

export async function listPendingIngredients(
  userId: number,
  signal?: AbortSignal,
): Promise<PendingIngredient[]> {
  return apiFetch<PendingIngredient[]>('/admin/pending-ingredients', {
    query: { user_id: userId },
    signal,
  })
}

export async function reviewRecipe(
  recipeId: number,
  userId: number,
  decision: 'approve' | 'reject',
): Promise<void> {
  await apiFetch(`/admin/recipes/${recipeId}/${decision}`, {
    method: 'POST',
    query: { user_id: userId },
  })
}

export async function reviewIngredient(
  submissionId: number,
  userId: number,
  decision: 'approve' | 'reject',
): Promise<void> {
  await apiFetch(`/admin/ingredients/${submissionId}/${decision}`, {
    method: 'POST',
    query: { user_id: userId },
  })
}
