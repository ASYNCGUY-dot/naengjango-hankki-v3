import { act, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
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

  it('조회 실패를 알리고 재시도하는 동안 같은 버튼의 초점을 유지한다', async () => {
    signIn()
    const user = userEvent.setup()
    let resolve!: (response: Response) => void
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(json({ detail: '오류' }, 500))
      .mockImplementationOnce(() => new Promise<Response>((done) => { resolve = done }))
    renderWithProviders(<NutritionFitCard recipeId={67} />)

    expect(await screen.findByRole('alert')).toHaveTextContent('영양 정보를 불러오지 못했어요')
    const retry = screen.getByRole('button', { name: '영양 정보 다시 불러오기' })
    await user.click(retry)
    expect(screen.getByRole('status')).toHaveTextContent('불러오는 중')
    expect(retry).toHaveFocus()
    expect(retry).toHaveAttribute('aria-disabled', 'true')
    await user.keyboard('{Enter}')
    expect(fetchMock).toHaveBeenCalledTimes(2)
    await act(async () => resolve(json(fit())))
    expect(await screen.findByText('단백질')).toBeInTheDocument()
    expect(retry).toHaveFocus()
    expect(retry).toHaveAttribute('aria-disabled', 'false')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('영양 재시도 중 다른 입력으로 이동하면 완료 후에도 그 초점을 유지한다', async () => {
    signIn()
    const user = userEvent.setup()
    let resolve!: (response: Response) => void
    vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(json({}, 502))
      .mockImplementationOnce(() => new Promise<Response>((done) => { resolve = done }))
    renderWithProviders(<><NutritionFitCard recipeId={67} /><input aria-label="후기 입력" /></>)
    await user.click(await screen.findByRole('button', { name: '영양 정보 다시 불러오기' }))
    const input = screen.getByLabelText('후기 입력')
    await user.click(input)
    await user.type(input, '후기 작성 중')
    await act(async () => resolve(json(fit())))
    expect(await screen.findByText('단백질')).toBeInTheDocument()
    expect(input).toHaveFocus()
    expect(input).toHaveValue('후기 작성 중')
  })

  it('다른 레시피로 이동한 뒤 도착한 이전 응답은 표시하지 않는다', async () => {
    signIn()
    const user = userEvent.setup()
    let resolveOld!: (response: Response) => void
    let resolveNew!: (response: Response) => void
    vi.spyOn(globalThis, 'fetch').mockImplementation((url) =>
      new Promise<Response>((done) => {
        if (String(url).includes('/67/')) resolveOld = done
        else resolveNew = done
      }),
    )
    function Fixture() {
      const [recipeId, setRecipeId] = useState(67)
      return <><button onClick={() => setRecipeId(68)}>다음 레시피</button><NutritionFitCard recipeId={recipeId} /></>
    }
    renderWithProviders(<Fixture />)
    expect(screen.getByRole('status')).toHaveTextContent('영양 정보를 불러오는 중')
    await user.click(screen.getByRole('button', { name: '다음 레시피' }))
    await act(async () => resolveNew(json(fit({ bracket_label: '새 레시피 기준' }))))
    expect(await screen.findByText('새 레시피 기준')).toBeInTheDocument()
    await act(async () => resolveOld(json(fit({ bracket_label: '이전 레시피 기준' }))))
    await waitFor(() => expect(screen.queryByText('이전 레시피 기준')).not.toBeInTheDocument())
    expect(screen.getByText('새 레시피 기준')).toBeInTheDocument()
  })
})
