import { act, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import RecipeCard, { type CardRecipe } from './RecipeCard'
import { renderWithProviders } from '../test/renderWithProviders'

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function signIn() {
  localStorage.setItem('naengjango.userId', '116')
  localStorage.setItem('naengjango.token', 'tok-test')
}

function recipe(id = 67, menuName = '김치볶음밥'): CardRecipe {
  return {
    id,
    menu_name: menuName,
    category: '밥',
    calorie: 320,
    image_url: 'https://example.test/recipe.jpg',
  }
}

function favorite(id = 67) {
  return { ...recipe(id), created_at: '2026-10-24T00:00:00' }
}

function deferredResponse() {
  let resolve!: (response: Response) => void
  const promise = new Promise<Response>((release) => { resolve = release })
  return { promise, resolve }
}

function CurrentRoute() {
  return <output aria-label="현재 경로">{useLocation().pathname}</output>
}

describe('레시피 사진의 즐겨찾기', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.restoreAllMocks())

  it('로그인 전에는 즐겨찾기를 조회하거나 버튼을 표시하지 않는다', () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
    renderWithProviders(<RecipeCard recipe={recipe()} />)

    expect(screen.queryByRole('button')).not.toBeInTheDocument()
    expect(fetchMock).not.toHaveBeenCalled()
    expect(screen.getByRole('link', { name: /김치볶음밥/ })).toHaveAttribute('href', '/recipe/67')
  })

  it('여러 카드가 즐겨찾기 목록을 한 번만 조회하고 실제 저장 상태를 표시한다', async () => {
    signIn()
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(json([favorite(68)]))
    renderWithProviders(<>
      <RecipeCard recipe={recipe()} />
      <RecipeCard recipe={recipe(68, '된장찌개')} />
      <RecipeCard recipe={recipe(69, '계란말이')} />
    </>)

    expect(await screen.findByRole('button', { name: '즐겨찾기 해제: 된장찌개' }))
      .toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: '즐겨찾기 추가: 김치볶음밥' }))
      .toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByRole('button', { name: '즐겨찾기 추가: 계란말이' }))
      .toHaveAttribute('aria-pressed', 'false')
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/favorites\/116$/)
  })

  it('별 버튼은 상세 링크 밖에 있으며 별을 누르면 현재 화면에 머무르고 카드를 누르면 상세로 간다', async () => {
    signIn()
    const user = userEvent.setup()
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (_input, init) =>
      init?.method === 'POST' ? json({ favorited: true }) : json([]),
    )
    renderWithProviders(<><RecipeCard recipe={recipe()} /><CurrentRoute /></>, { route: '/recipes' })

    const star = await screen.findByRole('button', { name: '즐겨찾기 추가: 김치볶음밥' })
    expect(star.closest('a')).toBeNull()
    await user.click(star)

    expect(screen.getByLabelText('현재 경로')).toHaveTextContent('/recipes')
    expect(await screen.findByRole('button', { name: '즐겨찾기 해제: 김치볶음밥' }))
      .toHaveAttribute('aria-pressed', 'true')
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(1)

    await user.click(screen.getByRole('link', { name: /김치볶음밥/ }))
    expect(screen.getByLabelText('현재 경로')).toHaveTextContent('/recipe/67')
  })

  it('같은 레시피의 모든 별이 즉시 함께 바뀌며 저장 중 다른 카드에서도 중복 요청을 막는다', async () => {
    signIn()
    const user = userEvent.setup()
    const pending = deferredResponse()
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (_input, init) =>
      init?.method === 'POST' ? pending.promise : json([]),
    )
    renderWithProviders(<>
      <RecipeCard recipe={recipe()} />
      <RecipeCard recipe={recipe()} />
    </>)

    const stars = await screen.findAllByRole('button', { name: '즐겨찾기 추가: 김치볶음밥' })
    await user.click(stars[0])

    const savedStars = screen.getAllByRole('button', { name: '즐겨찾기 해제: 김치볶음밥' })
    expect(savedStars).toHaveLength(2)
    for (const star of savedStars) {
      expect(star).toHaveAttribute('aria-pressed', 'true')
      expect(star).toHaveAttribute('aria-busy', 'true')
      expect(star).toBeDisabled()
    }
    await user.click(savedStars[1])
    await user.click(savedStars[0])
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(1)

    await act(async () => { pending.resolve(json({ favorited: true })) })
    for (const star of savedStars) {
      expect(star).toBeEnabled()
      expect(star).toHaveAttribute('aria-pressed', 'true')
    }
  })

  it('저장 실패 시 함께 표시된 별을 이전 상태로 되돌리고 오류를 알린다', async () => {
    signIn()
    const user = userEvent.setup()
    const pending = deferredResponse()
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (_input, init) =>
      init?.method === 'POST' ? pending.promise : json([]),
    )
    renderWithProviders(<>
      <RecipeCard recipe={recipe()} />
      <RecipeCard recipe={recipe()} />
    </>)

    const stars = await screen.findAllByRole('button', { name: '즐겨찾기 추가: 김치볶음밥' })
    await user.click(stars[0])
    expect(screen.getAllByRole('button', { name: '즐겨찾기 해제: 김치볶음밥' })).toHaveLength(2)
    await act(async () => { pending.resolve(json({ detail: '저장 오류' }, 500)) })

    for (const star of await screen.findAllByRole('button', { name: '즐겨찾기 추가: 김치볶음밥' })) {
      expect(star).toHaveAttribute('aria-pressed', 'false')
      expect(star).toBeEnabled()
    }
    expect(screen.getAllByRole('alert').some((alert) => alert.textContent?.includes('담지 못했어요')))
      .toBe(true)
  })

  it('목록 조회 실패를 빈 별로 오인시키지 않고 재시도하면 모든 카드 상태를 복구한다', async () => {
    signIn()
    const user = userEvent.setup()
    const initial = deferredResponse()
    const retry = deferredResponse()
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockImplementationOnce(() => initial.promise)
      .mockImplementationOnce(() => retry.promise)
    renderWithProviders(<>
      <RecipeCard recipe={recipe()} />
      <RecipeCard recipe={recipe(68, '된장찌개')} />
    </>)

    const loadingStar = screen.getByRole('button', { name: '즐겨찾기 불러오는 중: 김치볶음밥' })
    expect(loadingStar).not.toHaveAttribute('aria-pressed')
    await user.click(loadingStar)
    expect(fetchMock).toHaveBeenCalledTimes(1)

    await act(async () => { initial.resolve(json({ detail: '조회 오류' }, 500)) })
    const retryStar = await screen.findByRole('button', { name: '즐겨찾기 다시 불러오기: 김치볶음밥' })
    expect(screen.queryByRole('button', { pressed: false })).not.toBeInTheDocument()
    await user.click(retryStar)
    await user.click(retryStar)
    expect(fetchMock).toHaveBeenCalledTimes(2)

    await act(async () => { retry.resolve(json([favorite()])) })
    expect(await screen.findByRole('button', { name: '즐겨찾기 해제: 김치볶음밥' }))
      .toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: '즐겨찾기 추가: 된장찌개' }))
      .toHaveAttribute('aria-pressed', 'false')
    expect(fetchMock.mock.calls.every(([, init]) => init?.method !== 'POST')).toBe(true)
  })

  it.each(['{Enter}', ' '])('키보드 %s로 별을 눌러도 상세 페이지로 이동하지 않는다', async (key) => {
    signIn()
    const user = userEvent.setup()
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (_input, init) =>
      init?.method === 'POST' ? json({ favorited: true }) : json([]),
    )
    renderWithProviders(<><RecipeCard recipe={recipe()} /><CurrentRoute /></>, { route: '/recipes' })

    const star = await screen.findByRole('button', { name: '즐겨찾기 추가: 김치볶음밥' })
    star.focus()
    await user.keyboard(key)

    await waitFor(() => expect(star).toHaveAttribute('aria-pressed', 'true'))
    expect(screen.getByLabelText('현재 경로')).toHaveTextContent('/recipes')
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(1)
  })
})
