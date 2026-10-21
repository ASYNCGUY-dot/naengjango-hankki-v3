import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import ThemeRecipesPage from './테마목록'
import { getThemeRecipes, listThemes, PAGE_SIZE, type RecipeTheme } from '../api/recipes'

let entryNumber = 0

function page(offset = 0, total = 43, key = 'seasonal'): RecipeTheme {
  return {
    key,
    title: key === 'seasonal' ? '10월 제철' : '가볍게',
    subtitle: '단호박, 배가 제철이에요',
    total,
    recipes: Array.from({ length: Math.min(PAGE_SIZE, Math.max(0, total - offset)) }, (_, index) => ({
      id: offset + index + 1,
      menu_name: `제철 레시피 ${offset + index + 1}`,
      category: '반찬',
      calorie: 100,
      image_url: null,
    })),
  }
}

function response(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status, headers: { 'Content-Type': 'application/json' },
  })
}

function mockPages(handler?: (url: URL, init?: RequestInit) => Promise<Response> | Response) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = new URL(input as string)
    return handler?.(url, init) ?? response([page(Number(url.searchParams.get('offset')))])
  })
}

function show(route = '/themes/seasonal?month=10') {
  const router = createMemoryRouter([
    { path: '/themes/:themeKey', element: <ThemeRecipesPage /> },
    { path: '/recipe/:id', element: <h1>레시피 상세</h1> },
    { path: '/', element: <h1>홈</h1> },
  ], { initialEntries: [{ pathname: route.split('?')[0], search: route.includes('?') ? `?${route.split('?')[1]}` : '', key: `theme-test-${++entryNumber}` }] })
  render(<RouterProvider router={router} />)
  return router
}

afterEach(() => {
  vi.restoreAllMocks()
  vi.useRealTimers()
})

describe('테마 전체보기', () => {
  it('같은 월의 목록을 20개씩 누적하고 마지막 페이지에서 끝을 안내한다', async () => {
    const user = userEvent.setup()
    const fetchMock = mockPages()
    show()

    expect(await screen.findByRole('heading', { name: '10월 제철' })).toBeInTheDocument()
    expect(screen.getByText('전체 43개 중 20개')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '홈으로' })).toHaveAttribute('href', '/')
    await user.click(screen.getByRole('button', { name: '20개 더 보기' }))
    expect(await screen.findByText('전체 43개 중 40개')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /제철 레시피 21 / })).toHaveFocus()
    await user.click(screen.getByRole('button', { name: '3개 더 보기' }))

    expect(await screen.findByText('전체 43개 중 43개')).toBeInTheDocument()
    expect(within(screen.getByRole('list', { name: '레시피 목록' })).getAllByRole('listitem')).toHaveLength(43)
    expect(screen.getByText('모든 레시피를 확인했어요.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /더 보기/ })).not.toBeInTheDocument()
    expect(fetchMock.mock.calls.map(([url]) => {
      const query = new URL(url as string).searchParams
      return [query.get('theme'), query.get('month'), query.get('limit'), query.get('offset')]
    })).toEqual([
      ['seasonal', '10', '20', '0'],
      ['seasonal', '10', '20', '20'],
      ['seasonal', '10', '20', '40'],
    ])
  })

  it('더 보기 실패 후 이미 본 목록을 유지하며 같은 위치부터 다시 받는다', async () => {
    const user = userEvent.setup()
    let nextPageTries = 0
    const fetchMock = mockPages((url) => {
      const offset = Number(url.searchParams.get('offset'))
      if (offset === 20 && ++nextPageTries === 1) return response({ detail: '잠시 후 다시 시도해주세요.' }, 503)
      return response([page(offset)])
    })
    show()
    await screen.findByText('전체 43개 중 20개')
    const more = screen.getByRole('button', { name: '20개 더 보기' })
    await user.click(more)

    expect(await screen.findByRole('alert')).toHaveTextContent('잠시 후 다시 시도해주세요.')
    expect(screen.getByText('전체 43개 중 20개')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '다시 불러오기' })).toBe(more)
    expect(more).toHaveFocus()
    await user.click(more)

    expect(await screen.findByText('전체 43개 중 40개')).toBeInTheDocument()
    expect(fetchMock.mock.calls.map(([url]) => new URL(url as string).searchParams.get('offset'))).toEqual(['0', '20', '20'])
  })

  it('처음 조회 실패도 재시도할 수 있다', async () => {
    const user = userEvent.setup()
    let calls = 0
    mockPages(() => ++calls === 1 ? response({ detail: '일시 오류' }, 500) : response([page(0, 1)]))
    show()
    await screen.findByRole('alert')
    await user.click(screen.getByRole('button', { name: '다시 불러오기' }))
    expect(await screen.findByText('전체 1개 중 1개')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '10월 제철' })).toHaveFocus()
  })

  it('결과가 0개인 테마도 제목과 빈 상태를 보여준다', async () => {
    mockPages(() => response([page(0, 0)]))
    show()
    expect(await screen.findByRole('heading', { name: '10월 제철' })).toBeInTheDocument()
    expect(screen.getByText('이 테마에 해당하는 레시피가 아직 없어요.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /더 보기/ })).not.toBeInTheDocument()
  })

  it('월 없는 직접 링크는 진입 시의 월을 다음 페이지에서도 유지한다', async () => {
    const user = userEvent.setup()
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-10-31T23:59:00'))
    const fetchMock = mockPages()
    show('/themes/seasonal')
    await screen.findByText('전체 43개 중 20개')
    vi.setSystemTime(new Date('2026-11-01T00:01:00'))
    await user.click(screen.getByRole('button', { name: '20개 더 보기' }))
    await screen.findByText('전체 43개 중 40개')
    expect(fetchMock.mock.calls.every(([url]) => new URL(url as string).searchParams.get('month') === '10')).toBe(true)
  })

  it('테마를 이동한 뒤 도착한 이전 응답은 현재 목록을 덮어쓰지 않는다', async () => {
    let resolveOld!: (value: Response) => void
    let oldSignal: AbortSignal | null | undefined
    mockPages((url, init) => {
      if (url.searchParams.get('theme') === 'seasonal') {
        oldSignal = init?.signal
        return new Promise<Response>((resolve) => { resolveOld = resolve })
      }
      return response([page(0, 1, 'light')])
    })
    const router = show()
    await waitFor(() => expect(resolveOld).toBeDefined())
    await act(() => router.navigate('/themes/light?month=10'))
    expect(await screen.findByRole('heading', { name: '가볍게' })).toBeInTheDocument()
    await act(async () => resolveOld(response([page()])))
    expect(oldSignal?.aborted).toBe(true)
    expect(screen.getByRole('heading', { name: '가볍게' })).toBeInTheDocument()
    expect(screen.getByText('전체 1개 중 1개')).toBeInTheDocument()
  })

  it('더 보기 요청 중 연속 클릭을 막고 사용자가 옮긴 초점을 유지한다', async () => {
    const user = userEvent.setup()
    let resolveMore!: (value: Response) => void
    const fetchMock = mockPages((url) => Number(url.searchParams.get('offset')) === 0
      ? response([page()])
      : new Promise<Response>((resolve) => { resolveMore = resolve }))
    show()
    await screen.findByText('전체 43개 중 20개')
    const more = screen.getByRole('button', { name: '20개 더 보기' })
    await user.dblClick(more)
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(more).toHaveAttribute('aria-disabled', 'true')
    const home = screen.getByRole('link', { name: '홈으로' })
    act(() => home.focus())
    await act(async () => resolveMore(response([page(20)])))
    expect(home).toHaveFocus()
  })

  it('레시피 상세에서 뒤로 오면 더 본 목록을 복구한다', async () => {
    const user = userEvent.setup()
    const fetchMock = mockPages()
    const router = show()
    await screen.findByText('전체 43개 중 20개')
    await user.click(screen.getByRole('button', { name: '20개 더 보기' }))
    await screen.findByText('전체 43개 중 40개')
    await user.click(screen.getByRole('link', { name: /제철 레시피 27 / }))
    expect(await screen.findByRole('heading', { name: '레시피 상세' })).toBeInTheDocument()
    await act(() => router.navigate(-1))
    expect(await screen.findByText('전체 43개 중 40개')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it.each(['/themes/unknown?month=10', '/themes/seasonal?month=13', '/themes/seasonal?month=bad'])(
    '유효하지 않은 주소 %s는 서버에 보내지 않고 홈 이동을 제공한다', async (route) => {
      const fetchMock = mockPages()
      show(route)
      expect(screen.getByRole('heading', { name: '테마를 찾을 수 없어요' })).toBeInTheDocument()
      expect(screen.getByRole('link', { name: '홈으로' })).toHaveAttribute('href', '/')
      expect(fetchMock).not.toHaveBeenCalled()
    },
  )

  it('구형 서버가 여러 테마를 반환하면 전체 목록인 것처럼 보여주지 않는다', async () => {
    mockPages(() => response([page(0, 43), page(0, 1, 'light')]))
    show()
    expect(await screen.findByRole('alert')).toHaveTextContent('전체 목록을 확인할 수 없어요.')
    expect(screen.queryByRole('list', { name: '레시피 목록' })).not.toBeInTheDocument()
  })

  it('구형 서버가 10개 미리보기만 반환하면 완료된 목록으로 오인하지 않는다', async () => {
    mockPages(() => response([{ ...page(), recipes: page().recipes.slice(0, 10) }]))
    show()
    expect(await screen.findByRole('alert')).toHaveTextContent('전체 목록을 확인할 수 없어요.')
    expect(screen.queryByText('전체 43개 중 10개')).not.toBeInTheDocument()
  })

  it('서버가 offset을 무시한 경우 이전 레시피를 중복 추가하지 않는다', async () => {
    const user = userEvent.setup()
    mockPages(() => response([page()]))
    show()
    await screen.findByText('전체 43개 중 20개')
    await user.click(screen.getByRole('button', { name: '20개 더 보기' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('다음 레시피를 확인할 수 없어요.')
    expect(within(screen.getByRole('list', { name: '레시피 목록' })).getAllByRole('listitem')).toHaveLength(20)
  })
})

describe('테마 API 요청', () => {
  it('기존 홈 조회는 10개, 전체보기는 선택한 테마의 20개를 요청한다', async () => {
    const fetchMock = mockPages()
    await listThemes(undefined, 10)
    await getThemeRecipes({ theme: 'seasonal', month: 10, offset: 20 })
    const [home, detail] = fetchMock.mock.calls.map(([url]) => new URL(url as string).searchParams)
    expect(home.get('limit')).toBe('10')
    expect(home.get('theme')).toBeNull()
    expect(home.get('month')).toBe('10')
    expect(detail.get('theme')).toBe('seasonal')
    expect(detail.get('limit')).toBe('20')
    expect(detail.get('offset')).toBe('20')
  })
})
