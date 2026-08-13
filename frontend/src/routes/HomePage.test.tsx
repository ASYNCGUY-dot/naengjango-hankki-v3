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

/** 검색과 분류 목록 두 종류의 요청이 오므로 경로로 갈라서 답한다. */
function mockApi(handlers: {
  search?: (url: URL) => Recipe[]
  categories?: () => { category: string; count: number }[]
}) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = new URL(input as string)
    const body = url.pathname.endsWith('/categories')
      ? (handlers.categories?.() ?? [])
      : (handlers.search?.(url) ?? [])
    return new Response(JSON.stringify(body), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
  })
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
