import { apiFetch } from './client'
import type { components } from './schema'

export type MyRecipeItem = components['schemas']['MyRecipeItem']
export type MyRecipeDetail = components['schemas']['MyRecipeDetail']
export type RecipeSubmitRequest = components['schemas']['RecipeSubmitRequest']
export type RecipeSubmitResponse = components['schemas']['RecipeSubmitResponse']

/**
 * 내가 등록한 레시피. 상태(approved/pending)와 지금까지 받은 추천 수가 함께 온다.
 *
 * 등록 즉시 공개되는 것이 아니라 두 관문이 있다. 이름이 기존 레시피와 겹치면
 * status가 pending이 되어 관리자 승인을 기다리고, 승인된 뒤에도 추천이
 * 일정 수 쌓여야 다른 사람의 추천 후보에 들어간다. 그래서 목록에 두 값을 다 보여준다 -
 * 안 보여주면 "왜 내 레시피가 아무 데도 안 나오지"를 알 방법이 없다.
 */
export async function listMyRecipes(
  userId: number,
  signal?: AbortSignal,
): Promise<MyRecipeItem[]> {
  return apiFetch<MyRecipeItem[]>('/my-recipes', { query: { user_id: userId }, signal })
}

export async function getMyRecipe(
  recipeId: number,
  userId: number,
  signal?: AbortSignal,
): Promise<MyRecipeDetail> {
  return apiFetch<MyRecipeDetail>(`/my-recipes/${recipeId}`, {
    query: { user_id: userId },
    signal,
  })
}

export async function submitMyRecipe(
  userId: number,
  body: RecipeSubmitRequest,
): Promise<RecipeSubmitResponse> {
  return apiFetch<RecipeSubmitResponse>('/my-recipes', {
    method: 'POST',
    query: { user_id: userId },
    body,
  })
}

/**
 * 수정은 recipe_id를 유지한다. 지우고 다시 넣으면 쌓인 추천이 0으로 돌아가
 * 공개 상태가 풀리기 때문이다.
 */
export async function updateMyRecipe(
  recipeId: number,
  userId: number,
  body: RecipeSubmitRequest,
): Promise<RecipeSubmitResponse> {
  return apiFetch<RecipeSubmitResponse>(`/my-recipes/${recipeId}`, {
    method: 'PUT',
    query: { user_id: userId },
    body,
  })
}

export async function deleteMyRecipe(recipeId: number, userId: number): Promise<void> {
  await apiFetch(`/my-recipes/${recipeId}`, { method: 'DELETE', query: { user_id: userId } })
}
