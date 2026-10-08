import { screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import RecipeCostCard from './RecipeCostCard'
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
    tier: '가성비',
    matched: [],
    unmatched: [],
    total_cost: 3244.6,
    included: [
      { ingredient: '양파', matched_name: '양파', amount_g: 200, cost: 500, is_estimated: false, price_day: '당일 (09/30)' },
      { ingredient: '달걀', matched_name: '계란', amount_g: 120, cost: 800, is_estimated: true, price_day: '당일 (09/30)' },
      { ingredient: '돼지고기(삼겹살)', matched_name: '돼지', amount_g: 300, cost: 1944.6, is_estimated: false, price_day: '당일 (09/30)' },
    ],
    excluded: [
      { ingredient: '두부', reason: 'KAMIS 가격 매칭 안 됨' },
      { ingredient: '고추장', reason: 'KAMIS 가격 매칭 안 됨' },
    ],
    household_size: 2,
    basis: { provider: 'KAMIS 농산물유통정보(aT)', market: '서울 소매가', price_days: ['당일 (09/30)'] },
    ...overrides,
  }
}

describe('재료비 카드', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.restoreAllMocks())

  it('로그인하지 않으면 서버를 부르지 않고 안내만 한다', () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
    renderWithProviders(<RecipeCostCard recipeId={67} />)

    expect(screen.getByText(/로그인하면 KAMIS 농산물 시세로/)).toBeInTheDocument()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('재료비를 10원 단위로, 몇 인분 기준인지와 함께 보여준다', async () => {
    signIn()
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(body()))
    renderWithProviders(<RecipeCostCard recipeId={67} />)

    // 3244.6원 -> 3,240원. 1원 단위는 시세가 참고값인데 정밀한 척하는 것이다.
    expect(await screen.findByText('3,240원')).toBeInTheDocument()
    expect(screen.getByText(/2인분 기준 · 시세를 찾은 재료 3개/)).toBeInTheDocument()
  })

  it('어느 날, 어디 시세인지 서버가 준 그대로 밝힌다', async () => {
    signIn()
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(body()))
    renderWithProviders(<RecipeCostCard recipeId={67} />)

    expect(
      await screen.findByText(/KAMIS 농산물유통정보\(aT\) · 서울 소매가 · 당일 \(09\/30\) 기준/),
    ).toBeInTheDocument()
  })

  it('부분 합계라는 것과 빠진 재료를 숨기지 않는다', async () => {
    // 안 밝히면 "이 요리는 3천 원이면 되는구나"로 읽힌다.
    signIn()
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(body()))
    renderWithProviders(<RecipeCostCard recipeId={67} />)

    expect(await screen.findByText(/실제 장보기 비용보다 적게 나와요/)).toBeInTheDocument()
    expect(screen.getByText(/빠진 재료 2개: 두부 · 고추장/)).toBeInTheDocument()
  })

  it('무게로 환산한 재료에는 추정이라고 붙인다', async () => {
    signIn()
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(body()))
    renderWithProviders(<RecipeCostCard recipeId={67} />)

    await screen.findByText('3,240원')
    expect(screen.getAllByText('추정')).toHaveLength(1)
  })

  it('시세 날짜가 섞여 있으면 일부는 더 이전 값이라고 알린다', async () => {
    signIn()
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      json(body({ basis: { provider: 'KAMIS', market: '서울 소매가', price_days: ['당일 (09/30)', '1주일전 (09/23)'] } })),
    )
    renderWithProviders(<RecipeCostCard recipeId={67} />)

    expect(await screen.findByText(/일부 재료는 더 이전 시세/)).toBeInTheDocument()
  })

  it.each(['가성비', '기본', '프리미엄', '정보부족'])(
    '서버가 등급(%s)을 보내도 배지와 설명을 그리지 않고 금액만 보여준다',
    async (tier) => {
      // 등급은 실제 재료비와 거의 무관했다(2026-10-07 측정: 1인분 재료비 중앙값이 가성비
      // 774원·기본 816원·프리미엄 843원, 47원짜리 배물김치가 프리미엄). 금액 옆에 붙으면
      // 금액과 어긋나는 말을 하게 되므로 내렸다.
      signIn()
      vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(body({ tier })))
      renderWithProviders(<RecipeCostCard recipeId={67} />)

      await screen.findByText('3,240원')
      expect(screen.queryByText(tier)).not.toBeInTheDocument()
      expect(screen.queryByText(/같은 부류 시세/)).not.toBeInTheDocument()
    },
  )

  it('계산할 재료가 하나도 없으면 금액 대신 그렇다고 말한다', async () => {
    signIn()
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(body({ included: [], total_cost: 0 })))
    renderWithProviders(<RecipeCostCard recipeId={67} />)

    expect(await screen.findByText('KAMIS 시세로 계산할 수 있는 재료가 없어요.')).toBeInTheDocument()
    expect(screen.queryByText(/0원/)).not.toBeInTheDocument()
  })

  it('KAMIS가 응답하지 않으면(503) 잠시 뒤 다시 보라고 알린다', async () => {
    signIn()
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({ detail: 'KAMIS 응답 없음' }, 503))
    renderWithProviders(<RecipeCostCard recipeId={67} />)

    expect(await screen.findByText(/시세를 잠시 못 불러왔어요/)).toBeInTheDocument()
  })

  it('재료 수량 정보가 없는 레시피(404)에서는 카드를 숨긴다', async () => {
    signIn()
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({ detail: '수량 정보 없음' }, 404))
    const { container } = renderWithProviders(<RecipeCostCard recipeId={67} />)

    await vi.waitFor(() => expect(container.querySelector('section')).toBeNull())
  })

  it('응답 모양이 예상과 달라도 카드가 죽지 않는다', async () => {
    signIn()
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({ tier: '기본', total_cost: 0 }))
    renderWithProviders(<RecipeCostCard recipeId={67} />)

    expect(await screen.findByText('KAMIS 시세로 계산할 수 있는 재료가 없어요.')).toBeInTheDocument()
  })
})
