import { ApiError, apiFetch } from './client'
import type { components } from './schema'

export type MealEntry = components['schemas']['MealEntry']
export type DailyNutrition = components['schemas']['DailyNutritionResponse']
type MealCreate = components['schemas']['MealCreateRequest']

export const MEALS_CHANGED_EVENT = 'naengjango:meals-changed'

export function getMealErrorMessage(error: unknown, fallback: string): string {
  // 프로필이나 레시피가 없는 404와, 라우트 자체가 없는 기본 404를 구분한다.
  if (error instanceof ApiError && error.status === 404 && error.detail === 'Not Found') {
    return '현재 식사 기록 기능을 이용할 수 없어요. 잠시 후 다시 확인해 주세요.'
  }
  return fallback
}

function notifyChange() {
  window.dispatchEvent(new Event(MEALS_CHANGED_EVENT))
}

export function getTodayNutrition(signal?: AbortSignal): Promise<DailyNutrition> {
  return apiFetch<DailyNutrition>('/meals/today', { signal })
}

export async function createMeal(body: MealCreate): Promise<MealEntry> {
  const meal = await apiFetch<MealEntry>('/meals', { method: 'POST', body })
  notifyChange()
  return meal
}

export async function updateMeal(mealId: number, servings: number): Promise<MealEntry> {
  const meal = await apiFetch<MealEntry>(`/meals/${mealId}`, { method: 'PUT', body: { servings } })
  notifyChange()
  return meal
}

export async function deleteMeal(mealId: number): Promise<void> {
  await apiFetch<void>(`/meals/${mealId}`, { method: 'DELETE' })
  notifyChange()
}
