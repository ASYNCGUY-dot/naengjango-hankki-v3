import { apiFetch } from './client'
import type { components } from './schema'

export type RecipePrice = components['schemas']['PriceResponse']

/**
 * KAMIS 농산물 시세로 계산한 이 레시피의 재료비.
 *
 * 서버가 KAMIS 서울 소매가를 받아 재료마다 맞춰 보고, 프로필의 가구원 수로 환산해서
 * 더한다. 화면은 금액·기준 날짜·출처를 **받은 그대로** 보여준다 - 어느 날 시세인지를
 * 화면이 짐작해서 적으면 안 된다.
 *
 * KAMIS는 부류 6개를 차례로 부르는 느린 호출이라 첫 응답이 몇 초 걸릴 수 있다(서버가
 * 10분 동안 캐시한다). KAMIS가 응답하지 않으면 503이 온다.
 */
export async function getRecipePrice(
  recipeId: number,
  userId: number,
  signal?: AbortSignal,
): Promise<RecipePrice> {
  return apiFetch<RecipePrice>(`/recommendation/recipes/${recipeId}/price`, {
    query: { user_id: userId },
    signal,
  })
}

/**
 * 로그인 없이 보는 1인분 재료비 (2026-10-21). 레시피 링크를 받은 사람도 KAMIS 재료비를 볼 수
 * 있게 서버가 공개로 연 경로다. 가구원 수는 프로필에 있어서 항상 1인분이다.
 */
export async function getPublicRecipePrice(recipeId: number, signal?: AbortSignal): Promise<RecipePrice> {
  return apiFetch<RecipePrice>(`/recommendation/recipes/${recipeId}/price/public`, { signal })
}
