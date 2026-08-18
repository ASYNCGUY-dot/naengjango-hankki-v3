import { screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import NutritionFitCard from './NutritionFitCard'
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

function fit(overrides: Record<string, unknown> = {}) {
  return {
    available: true,
    bracket_label: '19-29세 기준',
    is_estimated: false,
    rows: [
      {
        key: 'protein_g',
        label: '단백질',
        unit: 'g',
        target: 55,
        provided: 3.4,
        pct_of_daily: 6,
        already_supplemented: false,
      },
    ],
    sodium_row: {
      label: '나트륨',
      unit: 'mg',
      limit: 2000,
      provided: 18.5,
      pct_of_limit: 1,
      limit_adjusted: true,
    },
    micro_is_partial: false,
    condition_notes: [],
    ...overrides,
  }
}

describe('나에게 맞는 영양', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.restoreAllMocks())

  it('로그인하지 않으면 서버를 부르지 않고 안내만 한다', () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
    renderWithProviders(<NutritionFitCard recipeId={67} />)

    expect(screen.getByRole('heading', { name: '나에게 맞는 영양' })).toBeInTheDocument()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('하루 권장량 대비로 보여준다', async () => {
    signIn()
    vi.spyOn(globalThis, 'fetch').mockImplementation(async () => json(fit()))
    renderWithProviders(<NutritionFitCard recipeId={67} />)

    expect(await screen.findByText('단백질')).toBeInTheDocument()
    expect(screen.getByText('19-29세 기준')).toBeInTheDocument()
    expect(screen.getByText('하루 권장량의 6%')).toBeInTheDocument()
    // 목표값에도 단위가 붙어야 한다. "3.4g / 55"는 55가 무엇인지 알 수 없다.
    expect(screen.getByText('/ 55g')).toBeInTheDocument()
  })

  it('나트륨은 채우는 목표가 아니라 상한으로 보여준다', async () => {
    // 다른 행과 같은 모양으로 그리면 "1%밖에 안 채웠네"로 잘못 읽힌다.
    signIn()
    vi.spyOn(globalThis, 'fetch').mockImplementation(async () => json(fit()))
    renderWithProviders(<NutritionFitCard recipeId={67} />)

    expect(await screen.findByText(/하루 상한의 1%/)).toBeInTheDocument()
    expect(screen.getByText(/하루 상한 2000mg/)).toBeInTheDocument()
  })

  it('병력으로 기준을 조정했으면 그 사실을 밝힌다', async () => {
    signIn()
    vi.spyOn(globalThis, 'fetch').mockImplementation(async () =>
      json(fit({ condition_notes: ['🩺 고혈압: 나트륨 상한을 하루 2000mg으로 적용했습니다.'] })),
    )
    renderWithProviders(<NutritionFitCard recipeId={67} />)

    expect(await screen.findByText(/고혈압/)).toBeInTheDocument()
    expect(screen.getByText(/병력 반영/)).toBeInTheDocument()
  })

  it('부분 합계라는 것을 반드시 알린다', async () => {
    // 지금 레시피 재료 중 22%만 영양DB와 매칭된다. 안 밝히면 "이 음식은 칼슘이
    // 적구나"라는 잘못된 결론으로 이어진다.
    signIn()
    vi.spyOn(globalThis, 'fetch').mockImplementation(async () =>
      json(fit({ micro_is_partial: true })),
    )
    renderWithProviders(<NutritionFitCard recipeId={67} />)

    expect(await screen.findByText(/실제보다 적게 나옵니다/)).toBeInTheDocument()
  })

  it('성인 평균으로 계산했으면 개인 기준인 척하지 않는다', async () => {
    signIn()
    vi.spyOn(globalThis, 'fetch').mockImplementation(async () =>
      json(fit({ is_estimated: true })),
    )
    renderWithProviders(<NutritionFitCard recipeId={67} />)

    expect(await screen.findByText(/성인 평균/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /입력하면 더 정확해져요/ })).toHaveAttribute(
      'href',
      '/onboarding',
    )
  })

  it('기준을 정할 수 없으면 입력하러 갈 길을 준다', async () => {
    signIn()
    vi.spyOn(globalThis, 'fetch').mockImplementation(async () =>
      json(fit({ available: false, rows: [], sodium_row: null })),
    )
    renderWithProviders(<NutritionFitCard recipeId={67} />)

    expect(await screen.findByRole('link', { name: '식단 정보 입력하기' })).toHaveAttribute(
      'href',
      '/onboarding',
    )
  })

  it('이 카드가 실패해도 레시피 화면을 망치지 않는다', async () => {
    signIn()
    vi.spyOn(globalThis, 'fetch').mockImplementation(async () => json({ detail: '오류' }, 500))
    const { container } = renderWithProviders(<NutritionFitCard recipeId={67} />)

    // 아무것도 안 그린다. 오류 문구로 레시피 본문을 가리지 않는다.
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(container.querySelector('section')).toBeNull()
  })
})
