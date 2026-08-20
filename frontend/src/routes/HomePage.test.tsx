import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import HomePage from './HomePage'
import { PAGE_SIZE } from '../api/recipes'
import { renderWithProviders } from '../test/renderWithProviders'

type Recipe = {
  id: number
  menu_name: string
  category: string | null
  calorie: number | null
  image_url: string | null
}

function recipe(id: number, overrides: Partial<Recipe> = {}): Recipe {
  return {
    id,
    menu_name: `레시피${id}`,
    category: '반찬',
    calorie: 100,
    image_url: `http://www.foodsafetykorea.go.kr/uploadimg/cook/${id}.png`,
    ...overrides,
  }
}

type Theme = {
  key: string
  title: string
  subtitle: string | null
  total: number
  recipes: Recipe[]
}

type Video = {
  video_title: string
  channel_title: string
  video_id: string
  thumbnail_url: string
  video_url: string
  view_count: number
  fetched_at: string
}

/** 검색·분류·테마·인기·영상 다섯 종류의 요청이 오므로 경로로 갈라서 답한다. */
function mockApi(handlers: {
  search?: (url: URL) => Recipe[]
  categories?: () => { category: string; count: number }[]
  themes?: () => Theme[]
  popular?: () => (Recipe & { like_count: number })[]
  videoCategories?: () => string[]
  videos?: () => Video[]
}) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = new URL(input as string)
    let body: unknown
    // 영상 쪽을 먼저 본다. "/popular-videos/categories"가 아래의 endsWith('/categories')에
    // 먼저 걸리면 분류 칩 자리에 영상 분류가 들어간다.
    if (url.pathname.startsWith('/popular-videos/categories')) {
      body = handlers.videoCategories?.() ?? []
    } else if (url.pathname.startsWith('/popular-videos/')) body = handlers.videos?.() ?? []
    else if (url.pathname.endsWith('/categories')) body = handlers.categories?.() ?? []
    else if (url.pathname.endsWith('/themes')) body = handlers.themes?.() ?? []
    else if (url.pathname.endsWith('/popular')) body = handlers.popular?.() ?? []
    else body = handlers.search?.(url) ?? []
    return new Response(JSON.stringify(body), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
  })
}

function video(overrides: Partial<Video> = {}): Video {
  return {
    video_title: '김치전을 바삭바삭하게!',
    channel_title: '백종원 PAIK JONG WON',
    video_id: '47OIcvpqxlo',
    thumbnail_url: 'https://i.ytimg.com/vi/47OIcvpqxlo/mqdefault.jpg',
    video_url: 'https://www.youtube.com/watch?v=47OIcvpqxlo',
    view_count: 11135969,
    fetched_at: '2026-07-16T22:14:28',
    ...overrides,
  }
}

describe('홈 화면', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('레시피 목록과 분류 칩을 보여준다', async () => {
    mockApi({
      search: () => [recipe(1, { menu_name: '두부조림' }), recipe(2, { menu_name: '된장국' })],
      categories: () => [
        { category: '반찬', count: 574 },
        { category: '일품', count: 171 },
      ],
    })
    renderWithProviders(<HomePage />)

    expect(await screen.findByText('두부조림')).toBeInTheDocument()
    expect(screen.getByText('된장국')).toBeInTheDocument()
    // "전체"는 서버가 주지 않고 화면이 앞에 붙인다.
    expect(screen.getByRole('button', { name: '전체' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: '반찬' })).toBeInTheDocument()
  })

  it('카드가 상세로 가는 링크다 — 링크 공유가 되는 화면', async () => {
    mockApi({ search: () => [recipe(67, { menu_name: '블랙빈 곤약국수' })] })
    renderWithProviders(<HomePage />)

    const link = await screen.findByRole('link', { name: /블랙빈 곤약국수/ })
    expect(link).toHaveAttribute('href', '/recipe/67')
  })

  it('사진 주소를 https로 바꿔서 넣는다', async () => {
    // 원본이 http라 https 페이지에서는 브라우저가 혼합 콘텐츠로 막는다.
    mockApi({ search: () => [recipe(1)] })
    const { container } = renderWithProviders(<HomePage />)

    await waitFor(() => {
      const img = container.querySelector('img')
      expect(img?.getAttribute('src')).toMatch(/^https:\/\//)
    })
  })

  it('사진이 없는 레시피도 깨지지 않는다', async () => {
    // image_url은 string | null이다. 1,148개 중 2개가 실제로 비어 있어서 개발 중에는
    // 거의 안 걸리고 실사용에서만 터진다.
    mockApi({ search: () => [recipe(1, { image_url: null, menu_name: '사진없는레시피' })] })
    const { container } = renderWithProviders(<HomePage />)

    expect(await screen.findByText('사진없는레시피')).toBeInTheDocument()
    expect(container.querySelector('img')).toBeNull()
  })

  it('칼로리가 없으면 kcal을 적지 않는다', async () => {
    mockApi({ search: () => [recipe(1, { calorie: null, category: '반찬' })] })
    renderWithProviders(<HomePage />)

    const card = await screen.findByRole('link', { name: /레시피1/ })
    expect(within(card).queryByText(/kcal/)).toBeNull()
    expect(within(card).getByText('반찬')).toBeInTheDocument()
  })

  it('분류를 고르면 그 분류로만 다시 조회한다', async () => {
    const user = userEvent.setup()
    const fetchMock = mockApi({
      search: () => [recipe(1)],
      categories: () => [{ category: '일품', count: 171 }],
    })
    renderWithProviders(<HomePage />)

    await user.click(await screen.findByRole('button', { name: '일품' }))

    await waitFor(() => {
      const urls = fetchMock.mock.calls.map((call) => new URL(call[0] as string))
      const last = urls.filter((u) => u.pathname.endsWith('/search')).at(-1)
      expect(last?.searchParams.get('category')).toBe('일품')
    })
  })

  it('"전체"를 고르면 분류를 보내지 않는다', async () => {
    // "전체"라는 문자열이 분류로 새어 들어가면 결과가 0개가 된다.
    const user = userEvent.setup()
    const fetchMock = mockApi({
      search: () => [recipe(1)],
      categories: () => [{ category: '반찬', count: 574 }],
    })
    renderWithProviders(<HomePage />)

    await user.click(await screen.findByRole('button', { name: '반찬' }))
    await user.click(screen.getByRole('button', { name: '전체' }))

    await waitFor(() => {
      const urls = fetchMock.mock.calls.map((call) => new URL(call[0] as string))
      const last = urls.filter((u) => u.pathname.endsWith('/search')).at(-1)
      expect(last?.searchParams.has('category')).toBe(false)
    })
  })

  it('결과가 없으면 빈 화면 대신 안내를 보여준다', async () => {
    mockApi({ search: () => [] })
    renderWithProviders(<HomePage />)

    expect(await screen.findByText(/조건에 맞는 레시피가 없어요/)).toBeInTheDocument()
  })

  it('한 쪽이 꽉 찼을 때만 더 보기를 띄우고, 누르면 이어붙인다', async () => {
    const user = userEvent.setup()
    const firstPage = Array.from({ length: PAGE_SIZE }, (_, i) => recipe(i + 1))
    const secondPage = [recipe(999, { menu_name: '다음쪽레시피' })]
    mockApi({
      search: (url) => (url.searchParams.get('offset') === '0' ? firstPage : secondPage),
    })
    renderWithProviders(<HomePage />)

    const more = await screen.findByRole('button', { name: '더 보기' })
    await user.click(more)

    expect(await screen.findByText('다음쪽레시피')).toBeInTheDocument()
    // 이전 쪽이 사라지면 안 된다.
    expect(screen.getByText('레시피1')).toBeInTheDocument()
    // 마지막 쪽이면 버튼이 사라진다.
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: '더 보기' })).not.toBeInTheDocument()
    })
  })

  it('조회에 실패하면 이유를 알린다', async () => {
    // 호출마다 Response를 새로 만든다. mockResolvedValue로 하나를 돌려쓰면 먼저 읽은
    // 요청이 본문을 소진해서, 뒤 요청은 빈 본문을 받는다(제품이 아니라 테스트 문제였다).
    vi.spyOn(globalThis, 'fetch').mockImplementation(
      async () =>
        new Response(JSON.stringify({ detail: '서버가 응답하지 않습니다.' }), {
          status: 503,
          headers: { 'Content-Type': 'application/json' },
        }),
    )
    renderWithProviders(<HomePage />)

    expect(await screen.findByRole('alert')).toHaveTextContent('서버가 응답하지 않습니다.')
  })

  it('분류 칩을 못 받아도 목록은 나온다', async () => {
    // 칩은 부가 정보다. 그것 때문에 화면 전체가 비면 안 된다.
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = new URL(input as string)
      if (url.pathname.endsWith('/categories')) {
        return new Response('{}', { status: 500 })
      }
      return new Response(JSON.stringify([recipe(1, { menu_name: '칩없어도보인다' })]), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    })
    renderWithProviders(<HomePage />)

    expect(await screen.findByText('칩없어도보인다')).toBeInTheDocument()
  })
})

describe('테마 줄', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.restoreAllMocks())

  function theme(overrides: Partial<Theme> = {}): Theme {
    return {
      key: 'light',
      title: '가볍게',
      subtitle: '200kcal 이하',
      total: 567,
      recipes: [recipe(11, { menu_name: '가벼운메뉴' })],
      ...overrides,
    }
  }

  it('테마를 제목·개수와 함께 줄로 보여준다', async () => {
    // 열 개만 보여주므로 전체가 몇 개인지 알려줘야 그게 전부인지 일부인지 안다.
    mockApi({ search: () => [recipe(1)], themes: () => [theme()] })
    renderWithProviders(<HomePage />)

    const section = await screen.findByRole('region', { name: '가볍게' })
    expect(within(section).getByText('567개')).toBeInTheDocument()
    expect(within(section).getByText('200kcal 이하')).toBeInTheDocument()
    expect(within(section).getByText('가벼운메뉴')).toBeInTheDocument()
  })

  it('검색하면 테마를 감춘다', async () => {
    // 찾는 게 분명한 사람에게 테마는 방해다.
    const user = userEvent.setup()
    mockApi({ search: () => [recipe(1)], themes: () => [theme()] })
    renderWithProviders(<HomePage />)

    await screen.findByRole('region', { name: '가볍게' })
    await user.type(screen.getByLabelText('레시피 검색'), '두부')

    await waitFor(() =>
      expect(screen.queryByRole('region', { name: '가볍게' })).not.toBeInTheDocument(),
    )
  })

  it('분류를 고르면 테마를 감춘다', async () => {
    const user = userEvent.setup()
    mockApi({
      search: () => [recipe(1)],
      themes: () => [theme()],
      categories: () => [{ category: '반찬', count: 574 }],
    })
    renderWithProviders(<HomePage />)

    await screen.findByRole('region', { name: '가볍게' })
    await user.click(await screen.findByRole('button', { name: '반찬' }))

    expect(screen.queryByRole('region', { name: '가볍게' })).not.toBeInTheDocument()
  })

  it('테마를 못 받아도 목록은 나온다', async () => {
    // 테마는 덤이다. 그것 때문에 화면 전체가 비면 안 된다.
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = new URL(input as string)
      if (url.pathname.endsWith('/themes')) return new Response('{}', { status: 500 })
      return new Response(JSON.stringify([recipe(1, { menu_name: '테마없어도보인다' })]), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    })
    renderWithProviders(<HomePage />)

    expect(await screen.findByText('테마없어도보인다')).toBeInTheDocument()
  })

  it('모양이 어긋난 테마가 와도 화면이 비지 않는다', async () => {
    // recipes가 없는 항목을 그대로 그리면 렌더링 중에 터져 화면 전체가 빈다.
    mockApi({
      search: () => [recipe(1, { menu_name: '망가져도보인다' })],
      themes: () => [{ key: 'broken', title: '깨진테마' } as unknown as Theme, theme()],
    })
    renderWithProviders(<HomePage />)

    expect(await screen.findByText('망가져도보인다')).toBeInTheDocument()
    expect(screen.queryByText('깨진테마')).not.toBeInTheDocument()
    expect(screen.getByRole('region', { name: '가볍게' })).toBeInTheDocument()
  })
})

describe('인기 요리 영상', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.restoreAllMocks())

  it('최상단에 영상을 보여주고 유튜브로 내보낸다', async () => {
    // "오늘 뭐 먹지"에 가장 빨리 답하는 것이 남이 이미 검증한 영상이라 맨 위에 둔다.
    // 우리 레시피와 연결이 없어서 카드가 아니라 외부 링크다.
    mockApi({ videoCategories: () => ['쉐프 레시피'], videos: () => [video()] })
    renderWithProviders(<HomePage />)

    const link = await screen.findByRole('link', { name: /김치전을 바삭바삭하게/ })
    expect(link).toHaveAttribute('href', 'https://www.youtube.com/watch?v=47OIcvpqxlo')
    expect(link).toHaveAttribute('target', '_blank')
    // opener를 넘기면 열린 쪽에서 우리 탭 주소를 바꿀 수 있다.
    expect(link.getAttribute('rel')).toContain('noopener')
  })

  it('분류를 고르면 그 분류의 영상을 다시 받는다', async () => {
    const user = userEvent.setup()
    const fetchMock = mockApi({
      videoCategories: () => ['쉐프 레시피', '자취요리'],
      videos: () => [video()],
    })
    renderWithProviders(<HomePage />)

    await user.click(await screen.findByRole('button', { name: '자취요리' }))

    await waitFor(() => {
      const called = fetchMock.mock.calls
        .map((call) => new URL(call[0] as string).pathname)
        .some((path) => path.includes(encodeURIComponent('자취요리')))
      expect(called).toBe(true)
    })
  })

  it('영상을 못 받으면 그 줄만 없고 목록은 나온다', async () => {
    // 유튜브 목록은 덤이다. 이것 때문에 홈이 비면 안 된다.
    mockApi({
      videoCategories: () => [],
      search: () => [recipe(1, { menu_name: '두부조림' })],
    })
    renderWithProviders(<HomePage />)

    expect(await screen.findByText('두부조림')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: '인기 요리 영상' })).not.toBeInTheDocument()
  })
})

describe('영상 줄이 이상한 응답을 받아도', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.restoreAllMocks())

  it('분류가 문자열이 아니어도 화면이 죽지 않는다', async () => {
    // 이걸 안 막으면 홈 전체가 빈 화면이 된다. 테마 줄에서 이미 한 번 겪은 실패다.
    mockApi({
      videoCategories: () => [recipe(1) as unknown as string],
      search: () => [recipe(2, { menu_name: '영상이상해도보인다' })],
    })
    renderWithProviders(<HomePage />)

    expect(await screen.findByText('영상이상해도보인다')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: '인기 요리 영상' })).not.toBeInTheDocument()
  })
})
