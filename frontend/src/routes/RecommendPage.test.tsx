import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import RecommendPage from './RecommendPage'
import { describeMatch, matchLevel, type RecommendationItem } from '../api/recommend'
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

function item(overrides: Partial<RecommendationItem> = {}): RecommendationItem {
  return {
    id: 1,
    menu_name: '고등어무조림',
    category: '일품',
    calorie: 320,
    nutrition_group: '단백질',
    image_url: 'http://x/1.png',
    youtube_url: null,
    ingredient_overlap: 3,
    // 카드가 "N개만 더 있으면 돼요"를 그리는 데 쓴다.
    missing_count: 2,
    coverage_ratio: 0.5,
    qualifies: true,
    has_protein_match: true,
    energy_kcal: 320,
    protein_g: null,
    fat_g: null,
    carbs_g: null,
    ...overrides,
  }
}

type PantryRow = { id: number; name: string; expiry_date: string | null }

/** 냉장고 조회와 추천 조회를 경로로 갈라 답한다. */
function mockApi(pantry: PantryRow[], recs: RecommendationItem[]) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = new URL(input as string)
    if (url.pathname.startsWith('/pantry/')) return json(pantry)
    return json(recs)
  })
}

describe('matchLevel / describeMatch', () => {
  it('자격 미달은 따로 구분한다', () => {
    // 서버가 qualifies=false로 표시한 항목은 겹치는 재료가 너무 적거나 메뉴명의 핵심
    // 재료가 없는 경우다. 구분하지 않으면 "왜 이게 추천됐지"가 된다.
    expect(matchLevel(item({ qualifies: false }))).toBe('poor')
    expect(matchLevel(item({ ingredient_overlap: 3 }))).toBe('good')
    expect(matchLevel(item({ ingredient_overlap: 1 }))).toBe('weak')
  })

  it('겹치는 재료가 없으면 그렇게 적는다', () => {
    expect(describeMatch(item({ ingredient_overlap: 0 }))).toBe('가진 재료 없이 만드는 메뉴')
    expect(describeMatch(item({ ingredient_overlap: 2 }))).toBe('재료 2개 활용')
  })
})

describe('추천 결과 화면', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.restoreAllMocks())

  it('로그인하지 않으면 아무 요청도 보내지 않는다', () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
    renderWithProviders(<RecommendPage />)

    expect(screen.getByText(/로그인이 필요해요/)).toBeInTheDocument()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('냉장고 재료를 읽어 추천 요청에 실어 보낸다', async () => {
    // 서버가 냉장고를 스스로 읽지 않으므로, 화면이 이 연결을 해야 한다.
    signIn()
    const fetchMock = mockApi(
      [
        { id: 1, name: '고등어', expiry_date: null },
        { id: 2, name: '무', expiry_date: null },
      ],
      [item()],
    )
    renderWithProviders(<RecommendPage />)

    await screen.findByText('고등어무조림')
    const recCall = fetchMock.mock.calls
      .map((c) => new URL(c[0] as string))
      .find((u) => u.pathname.startsWith('/recommendation/'))
    expect(recCall?.searchParams.getAll('ingredients')).toEqual(['고등어', '무'])
    // 기준 재료는 칩으로 보여준다 - 하나씩 뺄 수 있어야 하기 때문이다.
    expect(screen.getByRole('button', { name: '고등어 빼기' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '무 빼기' })).toBeInTheDocument()
  })

  it('재료 활용 개수를 카드에 표시한다', async () => {
    signIn()
    mockApi([{ id: 1, name: '고등어', expiry_date: null }], [item({ ingredient_overlap: 3 })])
    renderWithProviders(<RecommendPage />)

    const card = await screen.findByRole('link', { name: /고등어무조림/ })
    expect(within(card).getByText('재료 3개 활용')).toBeInTheDocument()
  })

  it('냉장고가 비면 추천을 부르지 않고 채우러 가라고 안내한다', async () => {
    // 재료가 없으면 서버가 후보 1,144개를 다 계산하고 아무것도 안 맞는 목록을 준다.
    signIn()
    const fetchMock = mockApi([], [])
    renderWithProviders(<RecommendPage />)

    expect(await screen.findByText(/냉장고가 비어 있어요/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '냉장고 채우러 가기' })).toHaveAttribute(
      'href',
      '/pantry',
    )
    const recCalls = fetchMock.mock.calls
      .map((c) => new URL(c[0] as string))
      .filter((u) => u.pathname.startsWith('/recommendation/'))
    expect(recCalls).toHaveLength(0)
  })

  it('결과가 비면 빈 화면 대신 안내한다', async () => {
    signIn()
    mockApi([{ id: 1, name: '고등어', expiry_date: null }], [])
    renderWithProviders(<RecommendPage />)

    expect(await screen.findByText(/맞는 메뉴를 찾지 못했어요/)).toBeInTheDocument()
  })

  it('실패하면 이유를 알린다', async () => {
    signIn()
    vi.spyOn(globalThis, 'fetch').mockImplementation(async () =>
      json({ detail: '서버에서 문제가 발생했습니다.' }, 500),
    )
    renderWithProviders(<RecommendPage />)

    expect(await screen.findByRole('alert')).toHaveTextContent('서버에서 문제가 발생했습니다.')
  })

  it('카드는 상세로 가는 링크다', async () => {
    signIn()
    mockApi([{ id: 1, name: '고등어', expiry_date: null }], [item({ id: 42 })])
    renderWithProviders(<RecommendPage />)

    const card = await screen.findByRole('link', { name: /고등어무조림/ })
    expect(card).toHaveAttribute('href', '/recipe/42')
  })

  it('사진이 없는 추천도 깨지지 않는다', async () => {
    signIn()
    mockApi(
      [{ id: 1, name: '고등어', expiry_date: null }],
      [item({ image_url: null, menu_name: '사진없는추천' })],
    )
    const { container } = renderWithProviders(<RecommendPage />)

    await screen.findByText('사진없는추천')
    await waitFor(() => expect(container.querySelector('img')).toBeNull())
  })
})

describe('기준 재료 편집', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.restoreAllMocks())

  const pantry = [
    { id: 1, name: '고등어', expiry_date: null },
    { id: 2, name: '무', expiry_date: null },
  ]

  function recCalls(fetchMock: ReturnType<typeof mockApi>) {
    return fetchMock.mock.calls
      .map((c) => new URL(c[0] as string))
      .filter((u) => u.pathname.startsWith('/recommendation/'))
  }

  it('재료를 빼도 바로 다시 부르지 않는다', async () => {
    // 추천 한 번이 무료 티어에서 2.4초다. 칩 하나 지울 때마다 부르면 편집이 괴로워진다.
    const user = userEvent.setup()
    signIn()
    const fetchMock = mockApi(pantry, [item()])
    renderWithProviders(<RecommendPage />)

    await screen.findByText('고등어무조림')
    expect(recCalls(fetchMock)).toHaveLength(1)

    await user.click(screen.getByRole('button', { name: '무 빼기' }))

    expect(screen.queryByRole('button', { name: '무 빼기' })).not.toBeInTheDocument()
    expect(recCalls(fetchMock)).toHaveLength(1)
  })

  it('고친 재료로 다시 추천받을 수 있다', async () => {
    const user = userEvent.setup()
    signIn()
    const fetchMock = mockApi(pantry, [item()])
    renderWithProviders(<RecommendPage />)

    await screen.findByText('고등어무조림')
    await user.click(screen.getByRole('button', { name: '무 빼기' }))
    await user.click(screen.getByRole('button', { name: '이 재료로 추천받기' }))

    await waitFor(() => expect(recCalls(fetchMock)).toHaveLength(2))
    expect(recCalls(fetchMock)[1].searchParams.getAll('ingredients')).toEqual(['고등어'])
  })

  it('없던 재료를 넣어 추천받을 수 있다', async () => {
    // 냉장고에 저장하지 않고 "이 재료만으로 뭘 만들지"를 보려는 용도다.
    const user = userEvent.setup()
    signIn()
    const fetchMock = mockApi(pantry, [item()])
    renderWithProviders(<RecommendPage />)

    await screen.findByText('고등어무조림')
    await user.type(screen.getByLabelText('재료 추가'), '두부')
    await user.click(screen.getByRole('button', { name: '추가' }))
    await user.click(screen.getByRole('button', { name: '이 재료로 추천받기' }))

    await waitFor(() => expect(recCalls(fetchMock)).toHaveLength(2))
    expect(recCalls(fetchMock)[1].searchParams.getAll('ingredients')).toEqual([
      '고등어',
      '무',
      '두부',
    ])
  })

  it('같은 재료를 두 번 넣지 않는다', async () => {
    // 중복이 들어가면 서버가 겹침 개수를 부풀려 센다.
    const user = userEvent.setup()
    signIn()
    mockApi(pantry, [item()])
    renderWithProviders(<RecommendPage />)

    await screen.findByText('고등어무조림')
    await user.type(screen.getByLabelText('재료 추가'), '고등어')
    await user.click(screen.getByRole('button', { name: '추가' }))

    expect(screen.getAllByRole('button', { name: '고등어 빼기' })).toHaveLength(1)
  })

  it('되돌리기는 고친 뒤에만 나타나고, 누르면 냉장고 재료로 돌아간다', async () => {
    const user = userEvent.setup()
    signIn()
    mockApi(pantry, [item()])
    renderWithProviders(<RecommendPage />)

    await screen.findByText('고등어무조림')
    // 안 고친 상태에서는 아무 일도 안 하는 버튼이라 감춘다.
    expect(
      screen.queryByRole('button', { name: '냉장고 재료로 되돌리기' }),
    ).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '무 빼기' }))
    await user.click(screen.getByRole('button', { name: '냉장고 재료로 되돌리기' }))

    expect(screen.getByRole('button', { name: '무 빼기' })).toBeInTheDocument()
  })

  it('편집해도 냉장고를 건드리지 않는다', async () => {
    // 이 화면의 편집은 이번 추천에만 쓰인다. 냉장고에 쓰기가 나가면 안 된다.
    const user = userEvent.setup()
    signIn()
    const fetchMock = mockApi(pantry, [item()])
    renderWithProviders(<RecommendPage />)

    await screen.findByText('고등어무조림')
    await user.click(screen.getByRole('button', { name: '무 빼기' }))
    await user.type(screen.getByLabelText('재료 추가'), '두부')
    await user.click(screen.getByRole('button', { name: '추가' }))
    await user.click(screen.getByRole('button', { name: '이 재료로 추천받기' }))

    await waitFor(() => expect(recCalls(fetchMock)).toHaveLength(2))
    const wrote = fetchMock.mock.calls.some(
      ([url, init]) =>
        String(url).includes('/pantry/') &&
        (init as RequestInit | undefined)?.method !== undefined &&
        (init as RequestInit).method !== 'GET',
    )
    expect(wrote).toBe(false)
  })
})
