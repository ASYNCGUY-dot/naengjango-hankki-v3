import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '../api/client'
import { getTodayNutrition, updateMeal, deleteMeal, MEALS_CHANGED_EVENT, type DailyNutrition, type MealEntry } from '../api/meals'
import { AuthContext, type AuthState } from '../auth/context'
import { renderWithProviders } from '../test/renderWithProviders'
import DailyNutritionCard from './DailyNutritionCard'

vi.mock('../api/meals', async (importOriginal) => ({
  ...await importOriginal<typeof import('../api/meals')>(),
  getTodayNutrition: vi.fn(),
  updateMeal: vi.fn(),
  deleteMeal: vi.fn(),
  MEALS_CHANGED_EVENT: 'naengjango:meals-changed',
}))

const meal: MealEntry = {
  id: 1, recipe_id: 67, recipe_name: '두부 김치', servings: 1,
  consumed_at: '2026-10-24T03:00:00Z',
}

function day(overrides: Partial<DailyNutrition> = {}): DailyNutrition {
  return {
    date: '2026-10-24', timezone: 'Asia/Seoul',
    server_now: '2026-10-24T03:00:00Z', next_reset_at: '2026-10-24T15:00:00Z',
    nutrition: {
      available: true, bracket_label: '19-29세 기준', is_estimated: false,
      rows: [{ key: 'protein_g', label: '단백질', unit: 'g', provided: 66, target: 55, pct_of_daily: 120, already_supplemented: false }],
      sodium_row: { label: '나트륨', unit: 'mg', provided: 500, limit: 2000, pct_of_limit: 25, limit_adjusted: false },
      micro_is_partial: false, condition_notes: [],
    },
    meals: [meal], incomplete_nutrients: [], ...overrides,
  }
}

function tomorrow(): DailyNutrition {
  const result = day({
    date: '2026-10-25', server_now: '2026-10-24T15:00:00Z', next_reset_at: '2026-10-25T15:00:00Z', meals: [],
  })
  result.nutrition.rows[0] = { ...result.nutrition.rows[0], provided: 0, pct_of_daily: 0 }
  return result
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((done, fail) => { resolve = done; reject = fail })
  return { promise, resolve, reject }
}

function signIn() {
  localStorage.setItem('naengjango.userId', '116')
  localStorage.setItem('naengjango.token', 'tok-test')
}

describe('오늘의 영양', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.mocked(getTodayNutrition).mockReset().mockResolvedValue(day())
    vi.mocked(updateMeal).mockReset().mockResolvedValue(meal)
    vi.mocked(deleteMeal).mockReset().mockResolvedValue(undefined)
  })
  afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks() })

  it('로그인하지 않으면 조회하지 않는다', () => {
    renderWithProviders(<DailyNutritionCard />)
    expect(getTodayNutrition).not.toHaveBeenCalled()
    expect(screen.queryByRole('heading', { name: '오늘의 영양' })).not.toBeInTheDocument()
  })

  it('실제 누적량과 초과 비율을 표시하되 바는 100%까지만 채우고 나트륨은 상한으로 분리한다', async () => {
    signIn()
    const result = day({ incomplete_nutrients: ['protein_g', 'sodium_mg'] })
    result.nutrition.is_estimated = true
    result.nutrition.micro_is_partial = true
    result.nutrition.rows[0].already_supplemented = true
    result.nutrition.condition_notes = ['등록한 병력에 따른 안내입니다.']
    vi.mocked(getTodayNutrition).mockResolvedValue(result)
    renderWithProviders(<DailyNutritionCard />)

    const bar = await screen.findByRole('progressbar', { name: '단백질' })
    expect(bar).toHaveAttribute('aria-valuenow', '100')
    expect(bar).toHaveAttribute('aria-valuetext', '66g, 하루 권장량의 120%')
    expect(bar.firstElementChild).toHaveStyle({ width: '100%' })
    expect(screen.getByText('하루 권장량의 120%')).toBeInTheDocument()
    expect(screen.getByText('/ 55g')).toBeInTheDocument()
    expect(screen.queryByRole('progressbar', { name: '나트륨' })).not.toBeInTheDocument()
    expect(screen.getByText('하루 상한의 25%를 섭취했어요.')).toBeInTheDocument()
    expect(screen.getByText('성인 평균')).toBeInTheDocument()
    expect(screen.getByText('영양제로 섭취 중')).toBeInTheDocument()
    expect(screen.getByText('등록한 병력에 따른 안내입니다.')).toBeInTheDocument()
    expect(screen.getByText(/실제보다 적게 나옵니다/)).toBeInTheDocument()
    expect(screen.getByText(/단백질·나트륨 정보가 없는 식사/)).toBeInTheDocument()
    expect(screen.getByText(/10월 24일/)).toHaveTextContent('한국 시간')
    expect(screen.getByRole('link', { name: '두부 김치' })).toHaveAttribute('href', '/recipe/67')
  })

  it('권장량 기준이 없어도 식사 기록을 보여주고 식단 정보 입력으로 안내한다', async () => {
    signIn()
    const result = day()
    result.nutrition.available = false
    result.nutrition.rows = []
    result.nutrition.sodium_row = null
    vi.mocked(getTodayNutrition).mockResolvedValue(result)
    renderWithProviders(<DailyNutritionCard />)
    expect(await screen.findByRole('link', { name: '식단 정보 입력하기' })).toHaveAttribute('href', '/onboarding')
    expect(screen.getByRole('link', { name: '두부 김치' })).toBeInTheDocument()
  })

  it('조회 실패 후 재시도하고 버튼 초점을 유지한다', async () => {
    signIn()
    const pending = deferred<DailyNutrition>()
    vi.mocked(getTodayNutrition).mockRejectedValueOnce(new Error('offline')).mockReturnValueOnce(pending.promise)
    const user = userEvent.setup()
    renderWithProviders(<DailyNutritionCard />)
    const retry = await screen.findByRole('button', { name: '오늘의 영양 다시 불러오기' })
    await user.click(retry)
    expect(retry).toHaveFocus()
    expect(retry).toHaveAttribute('aria-disabled', 'true')
    await user.keyboard('{Enter}')
    expect(getTodayNutrition).toHaveBeenCalledTimes(2)
    await act(async () => pending.resolve(day()))
    expect(screen.getByRole('progressbar')).toBeInTheDocument()
    expect(retry).toHaveFocus()
    expect(retry).toHaveAttribute('aria-disabled', 'false')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('식사 기록 기능을 제공하지 않으면 이용 불가를 안내하고 이후 다시 조회할 수 있다', async () => {
    signIn()
    vi.mocked(getTodayNutrition).mockRejectedValueOnce(new ApiError(404, 'Not Found'))
    const user = userEvent.setup()
    renderWithProviders(<DailyNutritionCard />)

    expect(await screen.findByRole('alert')).toHaveTextContent('현재 식사 기록 기능을 이용할 수 없어요. 잠시 후 다시 확인해 주세요.')
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '오늘의 영양 다시 불러오기' }))
    expect(await screen.findByRole('progressbar')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it.each([
    [404, '사용자 정보를 찾을 수 없습니다.'],
    [500, 'Not Found'],
  ])('실제 조회 오류(%i, %s)는 기능 미지원으로 안내하지 않는다', async (status, detail) => {
    signIn()
    vi.mocked(getTodayNutrition).mockRejectedValueOnce(new ApiError(status, detail))
    renderWithProviders(<DailyNutritionCard />)

    expect(await screen.findByRole('alert')).toHaveTextContent('오늘의 영양을 불러오지 못했어요. 다시 시도해 주세요.')
    expect(screen.getByRole('button', { name: '오늘의 영양 다시 불러오기' })).toBeInTheDocument()
  })

  it('서버에 저장된 임의 분량을 보존하고 수정 성공 후 합계를 다시 조회한다', async () => {
    signIn()
    const customMeal = { ...meal, servings: 0.75 }
    const updated = day({ meals: [{ ...meal, servings: 1.5 }] })
    updated.nutrition.rows[0] = { ...updated.nutrition.rows[0], provided: 99, pct_of_daily: 180 }
    vi.mocked(getTodayNutrition).mockResolvedValueOnce(day({ meals: [customMeal] })).mockResolvedValueOnce(updated)
    vi.mocked(updateMeal).mockImplementationOnce(async () => {
      window.dispatchEvent(new Event(MEALS_CHANGED_EVENT))
      return { ...meal, servings: 1.5 }
    })
    const user = userEvent.setup()
    renderWithProviders(<DailyNutritionCard />)
    const quantity = await screen.findByRole('combobox', { name: '먹은 양' })
    expect(quantity).toHaveValue('0.75')
    await user.selectOptions(quantity, '1.5')
    await user.click(screen.getByRole('button', { name: '저장' }))
    expect(updateMeal).toHaveBeenCalledWith(1, 1.5)
    expect(await screen.findByText('하루 권장량의 180%')).toBeInTheDocument()
    expect(getTodayNutrition).toHaveBeenCalledTimes(2)
    expect(screen.getByRole('status')).toHaveTextContent('먹은 양을 수정했어요.')
  })

  it('분량 수정 실패 시 입력과 기존 합계를 보존하여 다시 저장할 수 있다', async () => {
    signIn()
    vi.mocked(updateMeal).mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce({ ...meal, servings: 2 })
    vi.mocked(getTodayNutrition).mockResolvedValueOnce(day()).mockResolvedValueOnce(day({ meals: [{ ...meal, servings: 2 }] }))
    const user = userEvent.setup()
    renderWithProviders(<DailyNutritionCard />)
    const quantity = await screen.findByRole('combobox', { name: '먹은 양' })
    await user.selectOptions(quantity, '2')
    await user.click(screen.getByRole('button', { name: '저장' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('식사 기록을 변경하지 못했어요.')
    expect(quantity).toHaveValue('2')
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuetext', '66g, 하루 권장량의 120%')
    await user.click(screen.getByRole('button', { name: '저장' }))
    await waitFor(() => expect(getTodayNutrition).toHaveBeenCalledTimes(2))
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(updateMeal).toHaveBeenCalledTimes(2)
  })

  it('중복 음식도 별도 식사로 표시하고 취소 실패 후 지정한 기록만 다시 취소한다', async () => {
    signIn()
    const secondMeal = { ...meal, id: 2, servings: 2 }
    vi.mocked(getTodayNutrition).mockResolvedValueOnce(day({ meals: [meal, secondMeal] })).mockResolvedValueOnce(day({ meals: [secondMeal] }))
    vi.mocked(deleteMeal).mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce(undefined)
    const user = userEvent.setup()
    renderWithProviders(<DailyNutritionCard />)
    const list = await screen.findByRole('list', { name: '오늘 먹은 음식 2건' })
    const firstRow = within(list).getAllByRole('listitem')[0]
    await user.click(within(firstRow).getByRole('button', { name: '기록 취소' }))
    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(within(list).getAllByRole('listitem')).toHaveLength(2)
    await user.click(within(firstRow).getByRole('button', { name: '기록 취소' }))
    expect(await screen.findByRole('list', { name: '오늘 먹은 음식 1건' })).toBeInTheDocument()
    expect(deleteMeal).toHaveBeenNthCalledWith(1, 1)
    expect(deleteMeal).toHaveBeenNthCalledWith(2, 1)
    expect(screen.getByRole('combobox')).toHaveValue('2')
  })

  it('변경 알림 뒤 도착하는 오래된 조회 응답은 최신 합계를 덮어쓰지 않는다', async () => {
    signIn()
    const oldRequest = deferred<DailyNutrition>()
    vi.mocked(getTodayNutrition).mockReturnValueOnce(oldRequest.promise).mockResolvedValueOnce(day({ meals: [] }))
    renderWithProviders(<DailyNutritionCard />)
    const oldSignal = vi.mocked(getTodayNutrition).mock.calls[0][0]
    act(() => window.dispatchEvent(new Event(MEALS_CHANGED_EVENT)))
    expect(await screen.findByText(/아직 기록한 식사가 없어요/)).toBeInTheDocument()
    expect(oldSignal?.aborted).toBe(true)
    await act(async () => oldRequest.resolve(day()))
    expect(screen.queryByRole('link', { name: '두부 김치' })).not.toBeInTheDocument()
  })

  it('수정 후 합계 조회 실패 시 이전 수치를 숨기고 재시도로 실제 저장값을 가져온다', async () => {
    signIn()
    vi.mocked(getTodayNutrition).mockResolvedValueOnce(day()).mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce(day({ meals: [] }))
    const user = userEvent.setup()
    renderWithProviders(<DailyNutritionCard />)
    await user.click(await screen.findByRole('button', { name: '기록 취소' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('오늘의 영양을 불러오지 못했어요.')
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: '두부 김치' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '오늘의 영양 다시 불러오기' }))
    expect(await screen.findByText(/아직 기록한 식사가 없어요/)).toBeInTheDocument()
    expect(deleteMeal).toHaveBeenCalledTimes(1)
  })

  it('한국 자정에 서버 시간으로 갱신하며 PC의 시계가 달라도 새 하루를 표시한다', async () => {
    vi.useFakeTimers()
    // PC 시간은 서버와 다르다. 서버가 반환한 자정까지 남은 1초를 사용해야 한다.
    vi.setSystemTime(new Date('2020-01-01T00:00:00Z'))
    signIn()
    vi.mocked(getTodayNutrition).mockResolvedValueOnce(day({ server_now: '2026-10-24T14:59:59Z' })).mockResolvedValueOnce(tomorrow())
    renderWithProviders(<DailyNutritionCard />)
    await act(async () => {})
    expect(screen.getByText('하루 권장량의 120%')).toBeInTheDocument()
    await act(async () => { await vi.advanceTimersByTimeAsync(1000) })
    expect(getTodayNutrition).toHaveBeenCalledTimes(2)
    expect(screen.getByText('하루 권장량의 0%')).toBeInTheDocument()
    expect(screen.getByText(/10월 25일/)).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: '두부 김치' })).not.toBeInTheDocument()
  })

  it('자정 조회 실패 시 어제 값을 즉시 숨기고 화면 복귀 시 다시 조회한다', async () => {
    vi.useFakeTimers()
    signIn()
    vi.mocked(getTodayNutrition).mockResolvedValueOnce(day({ server_now: '2026-10-24T14:59:59Z' }))
      .mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce(tomorrow())
    renderWithProviders(<DailyNutritionCard />)
    await act(async () => {})
    await act(async () => { await vi.advanceTimersByTimeAsync(1000) })
    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: '두부 김치' })).not.toBeInTheDocument()
    await act(async () => { fireEvent(document, new Event('visibilitychange')) })
    expect(getTodayNutrition).toHaveBeenCalledTimes(3)
    expect(screen.getByText('하루 권장량의 0%')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('절전 중 자정을 넘기면 창 복귀에서 어제 합계를 숨긴 채 조회한다', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-10-24T14:59:59Z'))
    signIn()
    const newDay = deferred<DailyNutrition>()
    vi.mocked(getTodayNutrition).mockResolvedValueOnce(day({ server_now: '2026-10-24T14:59:59Z' })).mockReturnValueOnce(newDay.promise)
    renderWithProviders(<DailyNutritionCard />)
    await act(async () => {})
    // 타이머는 실행되지 않은 상태로 시계만 다음 날로 이동한다.
    vi.setSystemTime(new Date('2026-10-24T15:01:00Z'))
    act(() => fireEvent(window, new Event('focus')))
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: '두부 김치' })).not.toBeInTheDocument()
    await act(async () => newDay.resolve(tomorrow()))
    expect(screen.getByText('하루 권장량의 0%')).toBeInTheDocument()
  })

  it('계정 전환 시 합계를 즉시 지우고 이전 계정 요청과 늦은 변경 결과를 폐기한다', async () => {
    const pendingMutation = deferred<MealEntry>()
    const newAccount = deferred<DailyNutrition>()
    vi.mocked(getTodayNutrition).mockResolvedValueOnce(day()).mockReturnValueOnce(newAccount.promise)
    vi.mocked(updateMeal).mockReturnValueOnce(pendingMutation.promise)
    const auth = (userId: number): AuthState => ({
      userId, isAuthenticated: true, login: vi.fn(), signup: vi.fn(), logout: vi.fn(),
    })
    const content = (id: number) => <MemoryRouter><AuthContext.Provider value={auth(id)}><DailyNutritionCard /></AuthContext.Provider></MemoryRouter>
    const user = userEvent.setup()
    const view = render(content(116))
    await user.selectOptions(await screen.findByRole('combobox'), '2')
    await user.click(screen.getByRole('button', { name: '저장' }))
    view.rerender(content(117))
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: '두부 김치' })).not.toBeInTheDocument()
    await act(async () => pendingMutation.resolve({ ...meal, servings: 2 }))
    expect(getTodayNutrition).toHaveBeenCalledTimes(2)
    expect(screen.queryByText('먹은 양을 수정했어요.')).not.toBeInTheDocument()
    await act(async () => newAccount.resolve(day({ meals: [] })))
    expect(screen.getByText(/아직 기록한 식사가 없어요/)).toBeInTheDocument()
    view.unmount()
    act(() => window.dispatchEvent(new Event(MEALS_CHANGED_EVENT)))
    expect(getTodayNutrition).toHaveBeenCalledTimes(2)
  })
})
