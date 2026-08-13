import { apiFetch } from './client'
import type { components } from './schema'

export type RecipeDetail = components['schemas']['RecipeDetail']
export type RecipeIngredient = components['schemas']['RecipeIngredient']

export async function getRecipe(recipeId: number, signal?: AbortSignal): Promise<RecipeDetail> {
  return apiFetch<RecipeDetail>(`/recommendation/recipes/${recipeId}`, { signal })
}

export type Nutrients = {
  energy_kcal: number | null
  carbs_g: number | null
  protein_g: number | null
  fat_g: number | null
  sodium_mg: number | null
}

/**
 * nutrients_json은 문자열로 온다. 값도 숫자가 아니라 문자열인 경우가 있어서
 * (예: {"energy_kcal": "54.3"}) 화면에서 그대로 계산하면 문자열이 이어붙는다.
 */
export function parseNutrients(raw: string | null): Nutrients {
  const empty: Nutrients = {
    energy_kcal: null,
    carbs_g: null,
    protein_g: null,
    fat_g: null,
    sodium_mg: null,
  }
  if (!raw) return empty

  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    return empty
  }
  if (typeof parsed !== 'object' || parsed === null) return empty

  const source = parsed as Record<string, unknown>
  const toNumber = (value: unknown): number | null => {
    if (value === null || value === undefined || value === '') return null
    const num = Number(value)
    return Number.isFinite(num) ? num : null
  }

  return {
    energy_kcal: toNumber(source.energy_kcal),
    carbs_g: toNumber(source.carbs_g),
    protein_g: toNumber(source.protein_g),
    fat_g: toNumber(source.fat_g),
    sodium_mg: toNumber(source.sodium_mg),
  }
}

export type Step = { text: string; image: string | null }

/**
 * steps_json에서 조리 단계를 꺼낸다.
 *
 * 원본 텍스트에 이미 번호가 붙어 있다("1. 검은콩을 1시간 …"). 화면이 번호를 또 붙이면
 * "1. 1. …"이 되므로 여기서 접두 번호를 떼어낸다.
 */
export function parseSteps(raw: string | null): Step[] {
  if (!raw) return []

  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    return []
  }
  if (!Array.isArray(parsed)) return []

  return parsed
    .map((entry) => {
      const source = (entry ?? {}) as Record<string, unknown>
      const text = typeof source.text === 'string' ? stripLeadingNumber(source.text) : ''
      const image = typeof source.image === 'string' && source.image ? source.image : null
      return { text, image }
    })
    .filter((step) => step.text !== '')
}

function stripLeadingNumber(text: string): string {
  return text.replace(/^\s*\d+\s*[.)]\s*/, '').trim()
}

export type IngredientGroup = { title: string | null; items: RecipeIngredient[] }

/**
 * 재료를 구획별로 묶는다.
 *
 * 원본 데이터에 "주재료"·"장식" 같은 구획 제목이 재료처럼 섞여 있다(수량이 없는 행).
 * 그대로 나열하면 "주재료 —"가 재료 하나로 보인다.
 */
export function groupIngredients(ingredients: RecipeIngredient[]): IngredientGroup[] {
  const groups: IngredientGroup[] = []
  let current: IngredientGroup = { title: null, items: [] }

  for (const ingredient of ingredients) {
    const isHeading = ingredient.amount === null && ingredient.unit === null
    if (isHeading) {
      if (current.items.length > 0) groups.push(current)
      current = { title: ingredient.name, items: [] }
    } else {
      current.items.push(ingredient)
    }
  }
  if (current.items.length > 0) groups.push(current)
  return groups
}

/** "440 g"처럼 보여준다. 수량이 없으면 이름만 쓴다. */
export function describeAmount(ingredient: RecipeIngredient): string {
  if (ingredient.amount === null) return ''
  const amount = Number.isInteger(ingredient.amount)
    ? String(ingredient.amount)
    : ingredient.amount.toFixed(1)
  return ingredient.unit ? `${amount} ${ingredient.unit}` : amount
}
