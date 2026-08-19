import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import MyRecipesPage from './MyRecipesPage'
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

function item(overrides: Record<string, unknown> = {}) {
  return {
    id: 1197,
    menu_name: '치즈라면',
    category: '일품',
    calorie: 520,
    status: 'approved',
    like_count: 0,
    ...overrides,
  }
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
      return json({ recipe_id: 1, status: options.submitStatus ?? 'approved' })
    }
    if (method === 'DELETE') return json({ deleted: true })
    return json(options.items ?? [])
  })
}

describe('내 레시피', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.restoreAllMocks())

  it('로그인하지 않으면 아무 요청도 보내지 않는다', () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
    renderWithProviders(<MyRecipesPage />)

    expect(screen.getByRole('link', { name: '로그인하러 가기' })).toHaveAttribute('href', '/login')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('상태와 추천 수를 함께 보여준다', async () => {
    // 등록해도 바로 안 보이는 이유가 둘이다 - 승인 대기이거나 추천이 모자라거나.
    // 두 값을 안 보여주면 "왜 내 레시피가 아무 데도 안 나오지"에 답할 수 없다.
    signIn()
    mockApi({ items: [item({ status: 'pending', like_count: 2 })] })
    renderWithProviders(<MyRecipesPage />)

    const row = (await screen.findByText('치즈라면')).closest('li')
    expect(row).not.toBeNull()
    expect(within(row as HTMLElement).getByText('승인 대기')).toBeInTheDocument()
    expect(within(row as HTMLElement).getByText(/추천 2/)).toBeInTheDocument()
  })

  it('레시피 이름을 누르면 상세로 간다', async () => {
    signIn()
    mockApi({ items: [item()] })
    renderWithProviders(<MyRecipesPage />)

    expect(await screen.findByRole('link', { name: '치즈라면' })).toHaveAttribute(
      'href',
      '/recipe/1197',
    )
  })

  it('재료 이름을 통칭으로 적어달라고 알린다', async () => {
    // 여기 적은 이름에서 알레르기 태그를 뽑는다. 안 알리면 "달걀 2알"처럼 적어
    // 알레르기가 있는 사람에게 이 레시피가 안 걸러진다.
    const user = userEvent.setup()
    signIn()
    mockApi()
    renderWithProviders(<MyRecipesPage />)

    await user.click(await screen.findByRole('button', { name: '새 레시피 등록' }))

    expect(screen.getByText(/재료 이름은 통칭으로 적어주세요/)).toBeInTheDocument()
  })

  it('등록하면 무엇이 일어났는지 알려준다', async () => {
    const user = userEvent.setup()
    signIn()
    const fetchMock = mockApi()
    renderWithProviders(<MyRecipesPage />)

    await user.click(await screen.findByRole('button', { name: '새 레시피 등록' }))
    await user.type(screen.getByLabelText('메뉴 이름'), '내가만든볶음밥')
    await user.type(screen.getByLabelText(/재료/), '밥 1공기')
    await user.type(screen.getByLabelText(/조리 순서/), '볶는다')
    await user.click(screen.getByRole('button', { name: '등록하기' }))

    expect(await screen.findByRole('status')).toHaveTextContent('등록했어요')
    expect(postedBody(fetchMock)).toMatchObject({
      menu_name: '내가만든볶음밥',
      ingredients_text: '밥 1공기',
    })
  })

  it('이름이 겹쳐 승인 대기가 되면 그 사실을 알려준다', async () => {
    // 성공 문구만 띄우면 "등록했는데 왜 안 보이지"가 된다.
    const user = userEvent.setup()
    signIn()
    mockApi({ submitStatus: 'pending' })
    renderWithProviders(<MyRecipesPage />)

    await user.click(await screen.findByRole('button', { name: '새 레시피 등록' }))
    await user.type(screen.getByLabelText('메뉴 이름'), '두부조림')
    await user.type(screen.getByLabelText(/재료/), '두부 1모')
    await user.type(screen.getByLabelText(/조리 순서/), '졸인다')
    await user.click(screen.getByRole('button', { name: '등록하기' }))

    expect(await screen.findByRole('status')).toHaveTextContent('승인을 기다립니다')
  })

  it('열량을 비워두면 0이 아니라 모름으로 보낸다', async () => {
    // 0으로 보내면 열량 0kcal인 레시피가 만들어진다.
    const user = userEvent.setup()
    signIn()
    const fetchMock = mockApi()
    renderWithProviders(<MyRecipesPage />)

    await user.click(await screen.findByRole('button', { name: '새 레시피 등록' }))
    await user.type(screen.getByLabelText('메뉴 이름'), '열량모르는메뉴')
    await user.type(screen.getByLabelText(/재료/), '무 1개')
    await user.type(screen.getByLabelText(/조리 순서/), '끓인다')
    await user.click(screen.getByRole('button', { name: '등록하기' }))

    await waitFor(() => expect(postedBody(fetchMock).calorie).toBeNull())
  })
})
