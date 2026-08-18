import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import PantryPage from './PantryPage'
import { describeExpiry } from '../api/pantry'
import { renderWithProviders } from '../test/renderWithProviders'

type Item = { id: number; name: string; expiry_date: string | null }

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

/** 로그인 상태로 만든다. AuthProvider가 시작할 때 저장소를 읽는다. */
function signIn(userId = 15) {
  localStorage.setItem('naengjango.userId', String(userId))
  localStorage.setItem('naengjango.token', 'tok-test')
}

/** 요청 종류별로 답한다. 목록은 호출할 때마다 최신 상태를 돌려준다. */
function mockApi(
  getItems: () => Item[],
  overrides: { onWrite?: () => Response; suggestions?: () => unknown[] } = {},
) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const method = (init as RequestInit | undefined)?.method ?? 'GET'
    // 자동완성은 목록 조회와 같은 GET이라 경로로 갈라야 한다.
    if (String(input).includes('/pantry/suggest')) return json(overrides.suggestions?.() ?? [])
    if (method === 'GET') return json(getItems())
    return overrides.onWrite?.() ?? json({ ok: true })
  })
}

describe('describeExpiry', () => {
  const today = new Date('2026-08-13T09:00:00')

  it('유통기한이 없으면 아무것도 표시하지 않는다', () => {
    // 재료는 유통기한 없이도 등록할 수 있어서 없는 경우가 흔하다.
    expect(describeExpiry(null, today)).toBeNull()
  })

  it('남은 날짜를 세어준다', () => {
    expect(describeExpiry('2026-08-16', today)).toMatchObject({ label: '3일 남음', isSoon: true })
    expect(describeExpiry('2026-08-25', today)).toMatchObject({ label: '12일 남음', isSoon: false })
  })

  it('오늘과 지난 것을 구분한다', () => {
    expect(describeExpiry('2026-08-13', today)).toMatchObject({ label: '오늘까지', isSoon: true })
    expect(describeExpiry('2026-08-11', today)).toMatchObject({ label: '2일 지남', isPast: true })
  })

  it('시각이 달라도 날짜만 본다', () => {
    // 시각까지 비교하면 "오늘 자정 기준"과 어긋나 하루 차이가 난다.
    expect(describeExpiry('2026-08-14T23:00:00', today)?.label).toBe('1일 남음')
  })
})

describe('냉장고 화면', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.restoreAllMocks())

  it('로그인하지 않으면 목록을 부르지 않고 안내한다', () => {
    // 로그인 화면으로 밀어내면 둘러보다 들어온 사람이 왜 튕겼는지 모른다.
    const fetchMock = vi.spyOn(globalThis, 'fetch')
    renderWithProviders(<PantryPage />)

    expect(screen.getByText(/로그인이 필요해요/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '로그인하러 가기' })).toHaveAttribute('href', '/login')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('재료와 유통기한을 보여준다', async () => {
    signIn()
    mockApi(() => [
      { id: 1, name: '고등어', expiry_date: '2026-01-01' },
      { id: 2, name: '양파', expiry_date: null },
    ])
    renderWithProviders(<PantryPage />)

    expect(await screen.findByText('고등어')).toBeInTheDocument()
    expect(screen.getByText('양파')).toBeInTheDocument()
    // 유통기한이 지난 재료는 문구가 붙는다.
    expect(screen.getByText(/지남/)).toBeInTheDocument()
  })

  it('재료를 추가하면 서버에 보내고 목록을 다시 읽는다', async () => {
    const user = userEvent.setup()
    signIn()
    let items: Item[] = []
    const fetchMock = mockApi(
      () => items,
      { onWrite: () => { items = [{ id: 9, name: '두부', expiry_date: null }]; return json({ added: true }) } },
    )
    renderWithProviders(<PantryPage />)

    await waitFor(() => expect(screen.getByText(/아직 넣어둔 재료가 없어요/)).toBeInTheDocument())

    await user.type(screen.getByLabelText('재료 이름'), '두부')
    await user.click(screen.getByRole('button', { name: '추가' }))

    expect(await screen.findByText('두부')).toBeInTheDocument()
    const post = fetchMock.mock.calls.find((c) => (c[1] as RequestInit)?.method === 'POST')
    expect(post).toBeDefined()
    const sent = JSON.parse((post![1] as RequestInit).body as string)
    expect(sent).toEqual({ name: '두부', expiry_date: null })
  })

  it('이름이 비면 추가 버튼을 누를 수 없다', async () => {
    signIn()
    mockApi(() => [])
    renderWithProviders(<PantryPage />)

    await waitFor(() => expect(screen.getByRole('button', { name: '추가' })).toBeDisabled())
  })

  it('삭제하면 기다리지 않고 바로 사라진다', async () => {
    // 콜드스타트가 있는 서버라 응답을 기다리면 눌러도 반응이 없는 것처럼 보인다.
    const user = userEvent.setup()
    signIn()
    mockApi(() => [{ id: 1, name: '고등어', expiry_date: null }])
    renderWithProviders(<PantryPage />)

    await user.click(await screen.findByRole('button', { name: '고등어 삭제' }))

    expect(screen.queryByText('고등어')).not.toBeInTheDocument()
  })

  it('삭제가 실패하면 되돌리고 이유를 알린다', async () => {
    const user = userEvent.setup()
    signIn()
    mockApi(
      () => [{ id: 1, name: '고등어', expiry_date: null }],
      { onWrite: () => json({ detail: '삭제하지 못했습니다.' }, 500) },
    )
    renderWithProviders(<PantryPage />)

    await user.click(await screen.findByRole('button', { name: '고등어 삭제' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('삭제하지 못했습니다.')
    // 사라졌다가 돌아와야 한다 - 지워진 줄 알고 다시 넣으면 중복된다.
    expect(screen.getByText('고등어')).toBeInTheDocument()
  })

  it('유통기한을 바꾸면 서버에 보낸다', async () => {
    signIn()
    const fetchMock = mockApi(() => [{ id: 1, name: '고등어', expiry_date: null }])
    renderWithProviders(<PantryPage />)

    const input = await screen.findByLabelText('고등어 유통기한')
    const user = userEvent.setup()
    await user.type(input, '2026-09-01')

    await waitFor(() => {
      const put = fetchMock.mock.calls.find((c) => (c[1] as RequestInit)?.method === 'PUT')
      expect(put).toBeDefined()
    })
  })

  it('재료가 없으면 추천받기를 누를 수 없다', async () => {
    signIn()
    mockApi(() => [])
    renderWithProviders(<PantryPage />)

    await waitFor(() =>
      expect(screen.getByRole('button', { name: '이 재료로 추천받기' })).toBeDisabled(),
    )
  })

  it('임박한 재료 수를 요약에 보여준다', async () => {
    signIn()
    const soon = new Date()
    soon.setDate(soon.getDate() + 1)
    mockApi(() => [
      { id: 1, name: '고등어', expiry_date: soon.toISOString().slice(0, 10) },
      { id: 2, name: '양파', expiry_date: null },
    ])
    renderWithProviders(<PantryPage />)

    expect(await screen.findByText(/유통기한 임박 1개/)).toBeInTheDocument()
  })

  it('수량 조절은 두지 않는다', async () => {
    // ingredients 테이블에 수량 컬럼이 없고 추천도 이름만 쓴다. 화면에만 있고 아무 데도
    // 안 가는 조작을 두면 사용자는 저장된다고 믿는다.
    signIn()
    mockApi(() => [{ id: 1, name: '고등어', expiry_date: null }])
    renderWithProviders(<PantryPage />)

    await screen.findByText('고등어')
    expect(screen.queryByRole('button', { name: /늘리기|줄이기/ })).not.toBeInTheDocument()
  })
})

describe('재료 자동완성', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.restoreAllMocks())

  it('치는 동안 추천 이름을 보여주고, 고르면 입력창에 넣는다', async () => {
    // 손으로 치면 "돼지 고기"처럼 어느 레시피 태그와도 안 맞는 값이 들어간다.
    const user = userEvent.setup()
    signIn()
    mockApi(
      () => [],
      { suggestions: () => [{ name: '두부', recipe_count: 118 }] },
    )
    renderWithProviders(<PantryPage />)

    await user.type(screen.getByLabelText('재료 이름'), '두부')

    const suggestion = await screen.findByRole('button', { name: /두부/ })
    expect(suggestion).toHaveTextContent('레시피 118개')

    await user.click(suggestion)
    expect(screen.getByLabelText('재료 이름')).toHaveValue('두부')
  })

  it('입력창이 비면 추천을 부르지 않는다', async () => {
    // 빈 검색어로 1,762종을 다 내려받으면 첫 타자가 치기도 전에 목록이 열린다.
    signIn()
    const fetchMock = mockApi(() => [])
    renderWithProviders(<PantryPage />)

    await screen.findByLabelText('재료 이름')
    expect(
      fetchMock.mock.calls.some(([url]) => String(url).includes('/pantry/suggest')),
    ).toBe(false)
  })

  it('추천을 못 받아도 직접 쳐서 넣을 수 있다', async () => {
    const user = userEvent.setup()
    signIn()
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      if (String(input).includes('/pantry/suggest')) return json({ detail: '오류' }, 500)
      if (((init as RequestInit | undefined)?.method ?? 'GET') === 'GET') return json([])
      return json({ ok: true })
    })
    renderWithProviders(<PantryPage />)

    await user.type(screen.getByLabelText('재료 이름'), '두부')
    expect(screen.getByRole('button', { name: '추가' })).toBeEnabled()
  })
})
