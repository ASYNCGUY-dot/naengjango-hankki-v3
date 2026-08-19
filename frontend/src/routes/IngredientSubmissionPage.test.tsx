import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import IngredientSubmissionPage from './IngredientSubmissionPage'
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

type FetchMock = ReturnType<typeof mockApi>

/** 서버로 실제로 나간 등록 요청의 본문. 없으면 그 자체가 실패다. */
function postedBody(fetchMock: FetchMock): Record<string, unknown> {
  const call = fetchMock.mock.calls.find(([, init]) => (init as RequestInit)?.method === 'POST')
  if (call === undefined) throw new Error('등록 요청이 나가지 않았다')
  return JSON.parse((call[1] as RequestInit).body as string)
}

/** 목록(GET)과 등록(POST)을 method로 갈라 답한다. */
function mockApi(options: { items?: unknown[]; submitStatus?: string } = {}) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (_input, init) => {
    const method = (init as RequestInit | undefined)?.method
    if (method === 'POST' || method === 'PUT') {
      return json({ status: options.submitStatus ?? 'approved' })
    }
    return json(options.items ?? [])
  })
}

describe('재료 정보 등록', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.restoreAllMocks())

  it('로그인하지 않으면 아무 요청도 보내지 않는다', () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
    renderWithProviders(<IngredientSubmissionPage />)

    expect(screen.getByRole('link', { name: '로그인하러 가기' })).toHaveAttribute('href', '/login')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('영양 항목이 100g 기준이라는 것을 라벨에 적는다', async () => {
    // 단위를 오해하면 값 자체가 무의미해진다.
    const user = userEvent.setup()
    signIn()
    mockApi()
    renderWithProviders(<IngredientSubmissionPage />)

    await user.click(await screen.findByRole('button', { name: '새 재료 등록' }))

    expect(screen.getByLabelText('열량 (kcal / 100g)')).toBeInTheDocument()
    expect(screen.getByLabelText('나트륨 (mg / 100g)')).toBeInTheDocument()
  })

  it('빈 칸은 0이 아니라 모름으로 보낸다', async () => {
    // 0으로 보내면 열량 0kcal인 재료가 만들어져 남의 영양 계산까지 어긋난다.
    const user = userEvent.setup()
    signIn()
    const fetchMock = mockApi()
    renderWithProviders(<IngredientSubmissionPage />)

    await user.click(await screen.findByRole('button', { name: '새 재료 등록' }))
    await user.type(screen.getByLabelText('재료 이름'), '직접만든고추장')
    await user.type(screen.getByLabelText('열량 (kcal / 100g)'), '180')
    await user.click(screen.getByRole('button', { name: '등록하기' }))

    await waitFor(() => {
      const body = postedBody(fetchMock)
      expect(body.calorie).toBe(180)
      expect(body.sodium_mg).toBeNull()
    })
  })

  it('이미 있는 이름이면 승인 대기라는 것을 알려준다', async () => {
    const user = userEvent.setup()
    signIn()
    mockApi({ submitStatus: 'pending' })
    renderWithProviders(<IngredientSubmissionPage />)

    await user.click(await screen.findByRole('button', { name: '새 재료 등록' }))
    await user.type(screen.getByLabelText('재료 이름'), '두부')
    await user.click(screen.getByRole('button', { name: '등록하기' }))

    expect(await screen.findByRole('status')).toHaveTextContent('승인을 기다립니다')
  })

  it('내가 올린 재료의 상태를 보여준다', async () => {
    signIn()
    mockApi({
      items: [{ id: 3, ingredient_name: '할머니된장', calorie: 140, status: 'pending' }],
    })
    renderWithProviders(<IngredientSubmissionPage />)

    expect(await screen.findByText('할머니된장')).toBeInTheDocument()
    expect(screen.getByText('승인 대기')).toBeInTheDocument()
    expect(screen.getByText('140 kcal / 100g')).toBeInTheDocument()
  })
})
