import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App'
import { renderWithProviders } from './test/renderWithProviders'

function renderAt(route: string) {
  return renderWithProviders(<App />, { route })
}

/** 탭 화면은 로그인해야 열린다(AppLayout이 관문이다). */
function signIn(userId = 116) {
  localStorage.setItem('naengjango.userId', String(userId))
  localStorage.setItem('naengjango.token', 'tok-test')
}

/** 화면마다 부르는 곳이 달라서, 빈 배열로 답해두고 라우팅만 본다. */
function mockEmptyApi() {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(
    async () => new Response('[]', { status: 200, headers: { 'Content-Type': 'application/json' } }),
  )
}

describe('라우팅', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.restoreAllMocks())

  // V2는 화면 전체가 라우트 하나(/demo)였고 탭 전환을 State로만 처리했다.
  // 그래서 상세를 링크로 공유할 수 없었고 뒤로가기도 안 됐다. 여기서 그게 실제로
  // 고쳐졌는지 확인한다.

  it.each([
    ['/', '오늘 뭐 먹지?'],
    ['/pantry', '내 냉장고'],
    ['/recommend', '나를 위한 레시피 추천'],
    ['/brags', '자랑하기'],
    ['/my', '마이'],
  ])('로그인한 사람에게 %s 주소가 해당 화면을 연다', (route, heading) => {
    signIn()
    mockEmptyApi()
    renderAt(route)
    expect(screen.getByRole('heading', { level: 1, name: heading })).toBeInTheDocument()
  })

  it.each([
    ['/login', '냉장고 한끼'],
    ['/signup', '냉장고 한끼'],
  ])('%s 주소가 해당 화면을 연다', (route, heading) => {
    renderAt(route)
    expect(screen.getByRole('heading', { level: 1, name: heading })).toBeInTheDocument()
  })

  it('로그인하지 않으면 홈이 로그인 화면이다', () => {
    // 2026-08-20에 바뀐 구조다. 예전에는 비로그인도 홈에서 레시피를 둘러볼 수 있었다.
    renderAt('/')

    expect(screen.getByRole('heading', { level: 1, name: '냉장고 한끼' })).toBeInTheDocument()
    // 눌러도 전부 로그인 안내로 끝나는 탭을 보여주지 않는다.
    expect(screen.queryByRole('navigation', { name: '주요 메뉴' })).not.toBeInTheDocument()
  })

  it('레시피 상세는 로그인 없이도 열린다 — 링크로 공유되는 화면이다', async () => {
    // 이것이 V3 전환의 가장 큰 이득이라, 홈을 로그인 뒤로 옮기면서도 여기만 열어뒀다.
    // 주소의 67이 실제로 요청에 실려 나가는지까지 본다.
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(
      async (input) => {
        const path = new URL(input as string).pathname
        const body = path.startsWith('/recommendation/recipes/67')
          ? {
              id: 67,
              menu_name: '블랙빈 곤약국수',
              cook_method: null,
              category: null,
              calorie: null,
              nutrition_group: '단백질',
              nutrients_json: null,
              steps_json: null,
              youtube_url: null,
              image_url: null,
              ingredients: [],
              base_servings: null,
            }
          : []
        return new Response(JSON.stringify(body), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      },
    )

    renderAt('/recipe/67')

    expect(
      await screen.findByRole('heading', { level: 1, name: '블랙빈 곤약국수' }),
    ).toBeInTheDocument()
    expect(new URL(fetchMock.mock.calls[0][0] as string).pathname).toBe(
      '/recommendation/recipes/67',
    )
  })

  it('없는 주소는 홈으로 보낸다', () => {
    // 지인 테스트에서 오타 난 링크를 받아도 빈 화면을 보지 않게 한다.
    signIn()
    mockEmptyApi()
    renderAt('/이런주소는없다')
    expect(screen.getByRole('heading', { level: 1, name: '오늘 뭐 먹지?' })).toBeInTheDocument()
  })

  it('로그인 화면에는 하단 탭바를 두지 않는다', () => {
    renderAt('/login')
    expect(screen.queryByRole('navigation', { name: '주요 메뉴' })).not.toBeInTheDocument()
  })

  it('탭바로 화면을 옮기면 현재 위치가 표시된다', async () => {
    const user = userEvent.setup()
    signIn()
    mockEmptyApi()
    renderAt('/')

    await user.click(screen.getByRole('link', { name: '자랑하기' }))

    expect(screen.getByRole('heading', { level: 1, name: '자랑하기' })).toBeInTheDocument()
    // aria-current는 보조기기가 "지금 여기"를 읽어주는 근거다.
    expect(screen.getByRole('link', { name: '자랑하기' })).toHaveAttribute('aria-current', 'page')
  })

  it('냉장고는 탭이 아니라 마이 안에서 들어간다', async () => {
    // 매일 여는 화면이 아니라 가끔 정리하는 화면이라 네 칸 중 하나를 안 준다.
    const user = userEvent.setup()
    signIn()
    mockEmptyApi()
    renderAt('/my')

    expect(screen.queryByRole('link', { name: '냉장고' })).not.toBeInTheDocument()
    await user.click(await screen.findByRole('link', { name: /내 냉장고 재료/ }))

    expect(screen.getByRole('heading', { level: 1, name: '내 냉장고' })).toBeInTheDocument()
  })

  it('로그인과 회원가입 사이를 링크로 오간다', async () => {
    const user = userEvent.setup()
    renderAt('/login')

    await user.click(screen.getByRole('link', { name: '회원가입' }))
    expect(screen.getByRole('button', { name: '회원가입' })).toBeInTheDocument()

    await user.click(screen.getByRole('link', { name: '로그인' }))
    expect(screen.getByRole('button', { name: '로그인' })).toBeInTheDocument()
  })
})
