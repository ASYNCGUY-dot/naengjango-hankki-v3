import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import App from '../App'
import type { MealEntry } from '../api/meals'
import { dailyNutrition } from '../test/mealFixtures'
import { renderWithProviders } from '../test/renderWithProviders'

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

beforeEach(() => {
  localStorage.clear()
  localStorage.setItem('naengjango.userId', '116')
  localStorage.setItem('naengjango.token', 'test-token')
  vi.spyOn(window, 'scrollTo').mockImplementation(() => {})
})
afterEach(() => vi.restoreAllMocks())

it('레시피에서 먹은 양을 기록하면 마이의 서버 합계에 반영되고 수정·취소할 수 있다', async () => {
  let entries: MealEntry[] = []
  const writes: RequestInit[] = []
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const path = new URL(String(input)).pathname
    if (path === '/meals' && init?.method === 'POST') {
      writes.push(init)
      const body = JSON.parse(String(init.body))
      entries.push({ id: entries.length + 1, recipe_id: body.recipe_id, recipe_name: '두부덮밥', servings: body.servings, consumed_at: new Date().toISOString() })
      return json(entries.at(-1), 201)
    }
    if (path === '/meals/today') {
      const value = dailyNutrition({ meals: [...entries] })
      const provided = entries.reduce((sum, entry) => sum + entry.servings * 40, 0)
      value.nutrition.rows[0] = { ...value.nutrition.rows[0], provided, pct_of_daily: Math.round(provided / 55 * 100) }
      return json(value)
    }
    if (path === '/meals/1' && init?.method === 'PUT') {
      entries = entries.map(entry => ({ ...entry, servings: JSON.parse(String(init.body)).servings }))
      return json(entries[0])
    }
    if (path === '/meals/1' && init?.method === 'DELETE') {
      entries = []
      return new Response(null, { status: 204 })
    }
    if (path === '/recommendation/recipes/67') return json({
      id: 67, menu_name: '두부덮밥', category: '일품', calorie: 350, nutrition_group: '단백질',
      nutrients_json: JSON.stringify({ protein_g: 40, sodium_mg: 400 }),
      ingredients: [], steps_json: '[]', image_url: null, youtube_url: null, base_servings: 1,
    })
    if (path.startsWith('/profile/')) return json({ name: '테스트', username: 'tester', has_profile: true, is_admin: false })
    if (path.startsWith('/favorites/') || path.startsWith('/reviews/')) return json([])
    if (path.endsWith('/like')) return json({ liked: false, like_count: 0 })
    return json({ detail: '테스트에서 사용하지 않는 기능' }, 404)
  })
  const user = userEvent.setup()
  renderWithProviders(<App />, { route: '/recipe/67' })
  await screen.findByRole('heading', { level: 1, name: '두부덮밥' })
  expect(screen.queryByRole('heading', { name: '나에게 맞는 영양' })).not.toBeInTheDocument()
  await user.selectOptions(screen.getByLabelText('먹은 양'), '0.5')
  await user.click(screen.getByRole('button', { name: '먹었어요' }))
  await user.click(await screen.findByRole('link', { name: '마이에서 확인' }))

  const section = screen.getByRole('region', { name: '오늘의 영양' })
  expect(await within(section).findByRole('progressbar', { name: '단백질' })).toHaveAttribute('aria-valuenow', '36')
  expect(writes).toHaveLength(1)
  expect(writes[0].headers).toMatchObject({ Authorization: 'Bearer test-token' })
  expect(JSON.parse(String(writes[0].body))).toMatchObject({ recipe_id: 67, servings: 0.5, request_id: expect.any(String) })

  await user.selectOptions(within(section).getByLabelText('먹은 양'), '1.5')
  await user.click(within(section).getByRole('button', { name: '저장' }))
  await waitFor(() => expect(within(section).getByRole('progressbar', { name: '단백질' })).toHaveAttribute('aria-valuetext', '60g, 하루 권장량의 109%'))
  await user.click(within(section).getByRole('button', { name: '기록 취소' }))
  await waitFor(() => expect(within(section).getByRole('progressbar', { name: '단백질' })).toHaveAttribute('aria-valuenow', '0'))
  expect(entries).toHaveLength(0)
  expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/nutrition-fit'))).toBe(false)
})
