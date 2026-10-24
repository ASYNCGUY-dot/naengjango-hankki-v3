import { apiFetch } from './client'
import type { components } from './schema'

export type MealEntry = components['schemas']['MealEntry']
export type DailyNutrition = components['schemas']['DailyNutritionResponse']
type MealCreate = components['schemas']['MealCreateRequest']

export const MEALS_CHANGED_EVENT = 'naengjango:meals-changed'

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
