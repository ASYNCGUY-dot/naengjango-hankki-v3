import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import App from './App'
import { renderWithProviders } from './test/renderWithProviders'

function renderAt(route: string) {
  return renderWithProviders(<App />, { route })
}

describe('라우팅', () => {
  afterEach(() => vi.restoreAllMocks())

  // V2는 화면 전체가 라우트 하나(/demo)였고 탭 전환을 State로만 처리했다.
  // 그래서 상세를 링크로 공유할 수 없었고 뒤로가기도 안 됐다. 여기서 그게 실제로
  // 고쳐졌는지 확인한다.

  it.each([
    ['/', '오늘 뭐 먹지?'],
    ['/pantry', '내 냉장고'],
    ['/recommend', '추천 결과'],
    ['/login', '냉장고 한끼'],
    ['/signup', '냉장고 한끼'],
  ])('%s 주소가 해당 화면을 연다', (route, heading) => {
    renderAt(route)
    expect(screen.getByRole('heading', { level: 1, name: heading })).toBeInTheDocument()
  })

  it('레시피 상세는 주소의 id를 읽는다 — 링크로 공유되는 화면이 된다', async () => {
    // 주소의 67이 실제로 요청에 실려 나가는지까지 본다. 화면만 뜨고 엉뚱한 레시피를
    // 부르면 링크 공유가 성립하지 않는다.
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(
      async () =>
        new Response(
          JSON.stringify({
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
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ),
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
    renderAt('/이런주소는없다')
    expect(screen.getByRole('heading', { level: 1, name: '오늘 뭐 먹지?' })).toBeInTheDocument()
  })

  it('로그인 화면에는 하단 탭바를 두지 않는다', () => {
    renderAt('/login')
    expect(screen.queryByRole('navigation', { name: '주요 메뉴' })).not.toBeInTheDocument()
  })

  it('탭바로 화면을 옮기면 현재 위치가 표시된다', async () => {
    const user = userEvent.setup()
    renderAt('/')

    await user.click(screen.getByRole('link', { name: '냉장고' }))

    expect(screen.getByRole('heading', { level: 1, name: '내 냉장고' })).toBeInTheDocument()
    // aria-current는 보조기기가 "지금 여기"를 읽어주는 근거다.
    expect(screen.getByRole('link', { name: '냉장고' })).toHaveAttribute('aria-current', 'page')
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
