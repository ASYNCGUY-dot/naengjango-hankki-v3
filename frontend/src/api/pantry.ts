import { apiFetch } from './client'
import type { components } from './schema'

export type PantryItem = components['schemas']['PantryItem']

/** 서버가 유통기한이 가까운 순으로 준다(없는 것은 뒤로). 화면이 다시 정렬하지 않는다. */
export async function listPantry(userId: number, signal?: AbortSignal): Promise<PantryItem[]> {
  return apiFetch<PantryItem[]>(`/pantry/${userId}`, { signal })
}

export async function addPantryItem(
  userId: number,
  name: string,
  expiryDate: string | null,
): Promise<void> {
  const body: components['schemas']['PantryItemRequest'] = {
    name,
    expiry_date: expiryDate,
  }
  await apiFetch(`/pantry/${userId}`, { method: 'POST', body })
}

export async function updateExpiry(
  userId: number,
  ingredientId: number,
  expiryDate: string | null,
): Promise<void> {
  const body: components['schemas']['ExpiryUpdateRequest'] = { expiry_date: expiryDate }
  await apiFetch(`/pantry/${userId}/${ingredientId}`, { method: 'PUT', body })
}

export async function removePantryItem(userId: number, ingredientId: number): Promise<void> {
  await apiFetch(`/pantry/${userId}/${ingredientId}`, { method: 'DELETE' })
}

export type IngredientSuggestion = components['schemas']['IngredientSuggestion']

/**
 * 재료 이름 자동완성.
 *
 * 레시피 태그에서 뽑으므로 여기서 고른 이름은 추천에서 반드시 매칭된다. 손으로 치면
 * "돼지 고기"처럼 어디에도 안 맞는 값이 들어가고, 그러면 추천이 나빴을 때 알고리즘
 * 문제인지 입력 문제인지 갈라낼 수 없다.
 */
export async function suggestIngredients(
  keyword: string,
  signal?: AbortSignal,
): Promise<IngredientSuggestion[]> {
  return apiFetch<IngredientSuggestion[]>('/pantry/suggest', {
    query: { keyword },
    signal,
  })
}

/** 유통기한이 이 일수 이내면 임박으로 본다. */
export const EXPIRY_SOON_DAYS = 3

export type ExpiryState = { label: string; isSoon: boolean; isPast: boolean } | null

/**
 * 유통기한을 "2일 남음"처럼 읽을 수 있는 문구로 바꾼다.
 *
 * expiry_date는 string | null이다. 안 넣고 등록할 수 있으므로 없는 경우가 흔하다.
 * 날짜만 비교한다 - 시각까지 보면 "오늘 자정 기준"과 어긋나 하루 차이가 난다.
 */
export function describeExpiry(expiryDate: string | null, today = new Date()): ExpiryState {
  if (!expiryDate) return null

  const parsed = new Date(expiryDate)
  if (Number.isNaN(parsed.getTime())) return null

  const startOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate())
  const days = Math.round(
    (startOfDay(parsed).getTime() - startOfDay(today).getTime()) / 86_400_000,
  )

  if (days < 0) return { label: `${Math.abs(days)}일 지남`, isSoon: false, isPast: true }
  if (days === 0) return { label: '오늘까지', isSoon: true, isPast: false }
  return { label: `${days}일 남음`, isSoon: days <= EXPIRY_SOON_DAYS, isPast: false }
}
