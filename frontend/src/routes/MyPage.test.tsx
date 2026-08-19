import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import MyPage from './MyPage'
import { tokenStore } from '../api/client'
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

/** 프로필과 즐겨찾기 두 GET이 오므로 경로로 갈라 답한다. */
function mockApi(handlers: { profile?: () => unknown; favorites?: () => unknown[] } = {}) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    if (url.includes('/favorites/')) {
      if ((init as RequestInit | undefined)?.method === 'POST') return json({ favorited: true })
      return json(handlers.favorites?.() ?? [])
    }
    if ((init as RequestInit | undefined)?.method === 'POST') return json({ logged_out: true })
    return json(handlers.profile?.() ?? profile())
  })
}

function profile(overrides: Record<string, unknown> = {}) {
  return {
    has_profile: true,
    username: 'jisu',
    name: '최지수',
    gender: '여성',
    age_group: '20대',
    allergy: '',
    health_goal: '체중감량',
    purpose: null,
    cooking_level: null,
    supplements: null,
    household_size: null,
    novelty_pref: null,
    cooking_tools: null,
    medical_conditions: null,
    is_admin: false,
    ...overrides,
  }
}

describe('마이 화면', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.restoreAllMocks())

  it('로그인하지 않으면 로그인 안내를 보여준다', () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
    renderWithProviders(<MyPage />)

    expect(screen.getByRole('link', { name: '로그인하러 가기' })).toHaveAttribute('href', '/login')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('누구로 로그인했는지 보여준다', async () => {
    signIn()
    mockApi()
    renderWithProviders(<MyPage />)

    expect(await screen.findByText('최지수')).toBeInTheDocument()
    expect(screen.getByText('@jisu')).toBeInTheDocument()
  })

  it('로그아웃하면 토큰을 지운다', async () => {
    // logout()은 구현돼 있었는데 화면에서 부르는 곳이 없어 로그아웃할 방법이 없었다.
    const user = userEvent.setup()
    signIn()
    mockApi()
    renderWithProviders(<MyPage />)

    await user.click(await screen.findByRole('button', { name: '로그아웃' }))

    await waitFor(() => expect(tokenStore.get()).toBeNull())
  })

  it('서버 호출이 실패해도 이 기기에서는 로그아웃된다', async () => {
    // 예외가 새면 화면 상태가 로그인으로 남아, 토큰은 지워졌는데 아무것도 안 되는
    // 상태가 된다. 실제로 그랬고 미처리 거부 경고로 드러났다.
    const user = userEvent.setup()
    signIn()
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      if (String(input).includes('/favorites/')) return json([])
      return (init as RequestInit | undefined)?.method === 'POST'
        ? json({ detail: '서버 오류' }, 500)
        : json(profile())
    })
    renderWithProviders(<MyPage />)

    await user.click(await screen.findByRole('button', { name: '로그아웃' }))

    await waitFor(() => expect(tokenStore.get()).toBeNull())
    // 화면도 비로그인으로 바뀌어야 한다.
    await waitFor(() =>
      expect(screen.getByRole('link', { name: '로그인하러 가기' })).toBeInTheDocument(),
    )
  })

  it('온보딩을 안 했으면 알레르기가 반영되지 않는다고 알린다', async () => {
    // users.allergy가 NULL이면 알레르기 제외가 아예 돌지 않는다. 알레르기가 있는
    // 사람에게는 위험할 수 있어 눈에 띄게 알려야 한다.
    signIn()
    mockApi({ profile: () => profile({ has_profile: false }) })
    renderWithProviders(<MyPage />)

    const status = await screen.findByRole('status')
    expect(status).toHaveTextContent('식단 정보를 아직 입력하지 않으셨어요')
    expect(status).toHaveTextContent('알레르기')
    // 경고만 띄우고 갈 곳을 안 주면 사용자가 할 수 있는 게 없다.
    expect(screen.getByRole('link', { name: '식단 정보 입력하기' })).toHaveAttribute(
      'href',
      '/onboarding',
    )
  })

  it('온보딩을 마쳤으면 경고를 띄우지 않는다', async () => {
    signIn()
    mockApi()
    renderWithProviders(<MyPage />)

    await screen.findByText('최지수')
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
    // 알레르기가 바뀔 수 있으니 고친 뒤에도 다시 들어갈 길은 남겨둔다.
    expect(screen.getByRole('link', { name: '식단 정보 수정하기' })).toHaveAttribute(
      'href',
      '/onboarding',
    )
  })
})

describe('내가 등록한 것으로 가는 길', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.restoreAllMocks())

  it('내 레시피와 재료 등록으로 갈 수 있다', async () => {
    // 서버에는 V2 때부터 있었는데 여기로 가는 길이 없어 아무도 못 썼다(2026-08-19까지).
    signIn()
    mockApi()
    renderWithProviders(<MyPage />)

    expect(await screen.findByRole('link', { name: /내 레시피/ })).toHaveAttribute(
      'href',
      '/my/recipes',
    )
    expect(screen.getByRole('link', { name: /재료 정보 등록/ })).toHaveAttribute(
      'href',
      '/my/ingredients',
    )
  })

  it('관리자가 아니면 승인 대기 목록을 보여주지 않는다', async () => {
    signIn()
    mockApi()
    renderWithProviders(<MyPage />)

    await screen.findByText('최지수')
    expect(screen.queryByRole('link', { name: /승인 대기 목록/ })).not.toBeInTheDocument()
  })

  it('관리자에게만 승인 대기 목록을 보여준다', async () => {
    signIn()
    mockApi({ profile: () => profile({ is_admin: true }) })
    renderWithProviders(<MyPage />)

    expect(await screen.findByRole('link', { name: /승인 대기 목록/ })).toHaveAttribute(
      'href',
      '/admin',
    )
  })
})

describe('즐겨찾기', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.restoreAllMocks())

  it('담아둔 것이 없으면 어디서 담는지 알려준다', async () => {
    signIn()
    mockApi()
    renderWithProviders(<MyPage />)

    expect(await screen.findByText(/여기에 모여요/)).toBeInTheDocument()
  })

  it('담아둔 레시피를 카드로 보여주고 상세로 이어준다', async () => {
    // 이 기능이 없던 동안에는 마음에 든 레시피를 다시 찾을 방법이 검색뿐이었다.
    signIn()
    mockApi({
      favorites: () => [
        {
          id: 67,
          menu_name: '블랙빈 곤약국수',
          category: '일품',
          calorie: 54,
          image_url: null,
          created_at: '2026-08-18T00:00:00',
        },
      ],
    })
    renderWithProviders(<MyPage />)

    const card = await screen.findByRole('link', { name: /블랙빈 곤약국수/ })
    expect(card).toHaveAttribute('href', '/recipe/67')
  })

  it('즐겨찾기 목록을 못 받아도 계정 정보와 로그아웃은 보인다', async () => {
    signIn()
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      if (String(input).includes('/favorites/')) return json({ detail: '오류' }, 500)
      return json(profile())
    })
    renderWithProviders(<MyPage />)

    expect(await screen.findByText('최지수')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '로그아웃' })).toBeInTheDocument()
  })
})
