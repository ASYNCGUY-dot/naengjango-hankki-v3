import { screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import MissingIngredientsCard from './MissingIngredientsCard'
import { renderWithProviders } from '../test/renderWithProviders'

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function signIn(userId = 116) {
  localStorage.setItem('naengjango.userId', String(userId))
  localStorage.setItem('naengjango.token', 'tok-test')
}

function body(overrides: Record<string, unknown> = {}) {
  return {
    coverage: { total: 9, matched: 7, missing: 2, coverage_pct: 78 },
    missing_ingredients: [
      { ingredient: '달걀', suggestion: '대체 가능: 두부(식감 대체용)', type: 'substitute' },
      { ingredient: '호두', suggestion: '생략 가능 (실제 사용량 6g)', type: 'omit' },
    ],
    ...overrides,
  }
}

describe('지금 만들 수 있나요', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.restoreAllMocks())

  it('로그인하지 않으면 서버를 부르지 않고 안내만 한다', () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
    renderWithProviders(<MissingIngredientsCard recipeId={67} />)

    expect(screen.getByRole('heading', { name: '지금 만들 수 있나요?' })).toBeInTheDocument()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('부족한 재료를 이름과 대안까지 보여준다', async () => {
    // 추천 카드의 "2개만 더 있으면 돼요"가 여기서 "무엇이" 부족한지로 이어진다.
    signIn()
    vi.spyOn(globalThis, 'fetch').mockImplementation(async () => json(body()))
    renderWithProviders(<MissingIngredientsCard recipeId={67} />)

    expect(await screen.findByText('달걀')).toBeInTheDocument()
    expect(screen.getByText(/두부\(식감 대체용\)/)).toBeInTheDocument()
    expect(screen.getByText(/생략 가능/)).toBeInTheDocument()
    expect(screen.getByText('재료 78% 보유')).toBeInTheDocument()
  })

  it('다 있으면 그렇다고 말한다', async () => {
    signIn()
    vi.spyOn(globalThis, 'fetch').mockImplementation(async () =>
      json(body({ coverage: { total: 9, matched: 9, missing: 0, coverage_pct: 100 }, missing_ingredients: [] })),
    )
    renderWithProviders(<MissingIngredientsCard recipeId={67} />)

    expect(await screen.findByText(/냉장고에 다 있어요/)).toBeInTheDocument()
  })

  it('무엇을 기준으로 셌는지 밝힌다', async () => {
    // 안 적으면 "추천 화면에서 뺐는데 왜 아직 있지"가 된다.
    signIn()
    vi.spyOn(globalThis, 'fetch').mockImplementation(async () => json(body()))
    renderWithProviders(<MissingIngredientsCard recipeId={67} />)

    expect(await screen.findByText(/냉장고에 저장된 재료 기준/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '냉장고 고치기' })).toHaveAttribute('href', '/pantry')
  })

  it('이 카드가 실패해도 레시피 화면을 망치지 않는다', async () => {
    signIn()
    vi.spyOn(globalThis, 'fetch').mockImplementation(async () => json({ detail: '오류' }, 500))
    const { container } = renderWithProviders(<MissingIngredientsCard recipeId={67} />)

    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(container.querySelector('section')).toBeNull()
  })
})
