import { act, fireEvent, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import BragPage from './BragPage'
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

function brag(overrides: Record<string, unknown> = {}) {
  return {
    id: 1,
    recipe_id: 67,
    image_url: 'http://cdn/photo.jpg',
    body: '간이 딱 맞았어요.',
    created_at: '2026-08-20T09:30:00',
    username: 'jisu',
    menu_name: '블랙빈 곤약국수',
    recipe_image_url: null,
    like_count: 2,
    liked_by_me: false,
    ...overrides,
  }
}

/** 피드·프로필·좋아요를 경로와 method로 갈라 답한다. */
function mockApi(options: {
  brags?: unknown[]
  me?: string
  likeFails?: boolean
  deleteResponse?: () => Response | Promise<Response>
} = {}) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const path = new URL(input as string).pathname
    if ((init as RequestInit | undefined)?.method === 'POST') {
      if (options.likeFails) return json({ detail: '오류' }, 500)
      return json({ liked: true, like_count: 3 })
    }
    if ((init as RequestInit | undefined)?.method === 'DELETE') return options.deleteResponse?.() ?? json({ deleted: true })
    if (path.startsWith('/profile/')) return json({ has_profile: true, username: options.me ?? 'me' })
    return json(options.brags ?? [])
  })
}

describe('자랑하기 피드', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.restoreAllMocks())

  it('사진과 글, 그리고 그 레시피로 가는 길을 함께 보여준다', async () => {
    // 사진이 좋아 보이면 바로 그 레시피로 넘어가는 게 이 탭의 목적이다.
    signIn()
    mockApi({ brags: [brag()] })
    renderWithProviders(<BragPage />)

    expect(await screen.findByText('간이 딱 맞았어요.')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: /jisu님이 만든 블랙빈 곤약국수/ })).toBeInTheDocument()
    expect(screen.getByText('레시피 보기').closest('a')).toBe(screen.getByRole('link', { name: /블랙빈 곤약국수 레시피 보기/ }))
    expect(screen.getByRole('link', { name: /블랙빈 곤약국수 레시피 보기/ })).toHaveAttribute(
      'href',
      '/recipe/67',
    )
  })

  it('글 함께 읽기는 전체 글과 작성일을 보여주고 보기 설정을 저장한다', async () => {
    const user = userEvent.setup()
    signIn()
    mockApi({ brags: [brag()] })
    renderWithProviders(<BragPage />)
    await screen.findByText('간이 딱 맞았어요.')
    await user.click(screen.getByRole('button', { name: '글 함께 읽기' }))
    expect(screen.getByRole('button', { name: '글 함께 읽기' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByText('2026-08-20')).toBeInTheDocument()
    expect(localStorage.getItem('naengjango.feed-view')).toBe('reading')
    expect(screen.queryByRole('button', { name: '글 더보기' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '사진 모아보기' }))
    expect(localStorage.getItem('naengjango.feed-view')).toBe('photos')
  })

  it('사진 주소를 https로 바꿔서 넣는다', async () => {
    // 원본이 http면 https 페이지에서 브라우저가 혼합 콘텐츠로 막는다.
    signIn()
    mockApi({ brags: [brag()] })
    renderWithProviders(<BragPage />)

    const img = await screen.findByRole('img', { name: /jisu님이 만든/ })
    expect(img.getAttribute('src')).toMatch(/^https:\/\//)
  })

  it('사진 없는 글도 깨지지 않는다', async () => {
    signIn()
    mockApi({ brags: [brag({ image_url: null, body: '사진없는자랑' })] })
    const { container } = renderWithProviders(<BragPage />)

    expect(await screen.findByText('사진없는자랑')).toBeInTheDocument()
    await waitFor(() => expect(container.querySelector('img')).toBeNull())
  })

  it('사진을 불러오지 못해도 메뉴 이름과 레시피 링크는 남긴다', async () => {
    signIn()
    mockApi({ brags: [brag()] })
    renderWithProviders(<BragPage />)

    fireEvent.error(await screen.findByRole('img', { name: /jisu님이 만든/ }))

    expect(screen.queryByRole('img')).not.toBeInTheDocument()
    expect(screen.getByText('블랙빈 곤약국수')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '블랙빈 곤약국수 레시피 보기' })).toHaveAttribute(
      'href',
      '/recipe/67',
    )
  })

  it('두 줄을 실제로 넘치는 글은 펼쳐 읽고 다시 접을 수 있다', async () => {
    const user = userEvent.setup()
    signIn()
    const body = '냉장고에 남아 있던 재료를 모아서 만들었어요. 내일 도시락까지 든든하게 준비했어요.'
    vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(42)
    vi.spyOn(HTMLElement.prototype, 'scrollHeight', 'get').mockReturnValue(84)
    mockApi({ brags: [brag({ body })] })
    renderWithProviders(<BragPage />)

    const expand = await screen.findByRole('button', { name: '글 더보기' })
    expect(expand).toHaveAttribute('aria-expanded', 'false')
    await user.click(expand)

    expect(screen.getByRole('button', { name: '글 접기' })).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText(body)).toBeInTheDocument()
    expect(screen.getByText('2026-08-20')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '글 접기' }))
    expect(screen.getByRole('button', { name: '글 더보기' })).toHaveAttribute('aria-expanded', 'false')
  })

  it('글자 수가 길어도 두 줄 안에 들어오면 글 더보기를 보여주지 않는다', async () => {
    signIn()
    const body = '남은 재료로 든든한 한 끼를 만들었어요.'
    vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(42)
    vi.spyOn(HTMLElement.prototype, 'scrollHeight', 'get').mockReturnValue(42)
    mockApi({ brags: [brag({ body })] })
    renderWithProviders(<BragPage />)

    expect(await screen.findByText(body)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '글 더보기' })).not.toBeInTheDocument()
  })

  it('화면 크기 변화로 짧은 글이 잘리면 글 더보기를 추가한다', async () => {
    signIn()
    const body = '달걀 두 개의 저녁'
    let contentHeight = 42
    vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(42)
    vi.spyOn(HTMLElement.prototype, 'scrollHeight', 'get').mockImplementation(() => contentHeight)
    mockApi({ brags: [brag({ body })] })
    renderWithProviders(<BragPage />)

    expect(await screen.findByText(body)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '글 더보기' })).not.toBeInTheDocument()

    contentHeight = 63
    fireEvent(window, new Event('resize'))

    expect(screen.getByRole('button', { name: '글 더보기' })).toBeInTheDocument()
  })

  it('누르면 서버 응답을 기다리지 않고 먼저 바뀐다', async () => {
    // 무료 서버에서 왕복이 2초 넘게 걸린다. 그동안 그대로면 또 눌러서 취소된다.
    const user = userEvent.setup()
    signIn()
    mockApi({ brags: [brag()] })
    renderWithProviders(<BragPage />)

    await user.click(await screen.findByRole('button', { name: /좋아요/ }))

    expect(screen.getByRole('button', { name: /좋아요/ })).toHaveAttribute('aria-pressed', 'true')
  })

  it('좋아요에 실패하면 숫자까지 되돌리고 알린다', async () => {
    const user = userEvent.setup()
    signIn()
    mockApi({ brags: [brag()], likeFails: true })
    renderWithProviders(<BragPage />)

    await user.click(await screen.findByRole('button', { name: /좋아요/ }))

    expect(await screen.findByRole('alert')).toHaveTextContent('좋아요를 누르지 못했어요')
    await waitFor(() => {
      const button = screen.getByRole('button', { name: /좋아요/ })
      expect(button).toHaveAttribute('aria-pressed', 'false')
      expect(button).toHaveTextContent('2')
    })
  })

  it('더 보기로 이어붙일 때 겹치는 글을 두 번 넣지 않는다', async () => {
    // offset은 첫 쪽을 받은 시점의 개수다. 그 사이 누가 올리면 목록이 밀려서 같은
    // 글이 두 번 온다. 그러면 React key가 겹쳐 화면이 어긋난다.
    const user = userEvent.setup()
    signIn()
    const firstPage = Array.from({ length: 20 }, (_, i) => brag({ id: i + 1 }))
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = new URL(input as string)
      if (url.pathname.startsWith('/profile/')) return json({ has_profile: true, username: 'me' })
      // 두 번째 쪽이 첫 쪽의 마지막 글을 다시 준다(밀린 상황).
      return json(
        url.searchParams.get('offset') === '20'
          ? [brag({ id: 20 }), brag({ id: 21, body: '진짜 새 글' })]
          : firstPage,
      )
    })
    renderWithProviders(<BragPage />)

    await user.click(await screen.findByRole('button', { name: '더 보기' }))

    expect(await screen.findByText('진짜 새 글')).toBeInTheDocument()
    // id 20이 두 번 들어가면 21장이 된다.
    await waitFor(() =>
      expect(screen.getAllByRole('link', { name: /레시피 보기/ })).toHaveLength(21),
    )
  })

  it('내 글에만 삭제를 보여준다', async () => {
    signIn()
    mockApi({ brags: [brag({ username: 'jisu' }), brag({ id: 2, username: '남' })], me: 'jisu' })
    renderWithProviders(<BragPage />)

    await screen.findAllByText('간이 딱 맞았어요.')
    // 두 글 중 내 것 하나에만 버튼이 있어야 한다.
    await waitFor(() => expect(screen.getAllByRole('button', { name: '이 글 삭제: 블랙빈 곤약국수' })).toHaveLength(1))
    expect(screen.getByRole('button', { name: '이 글 삭제: 블랙빈 곤약국수' })).toHaveTextContent('이 글 삭제')
  })

  it('삭제는 확인을 받고 나서만 보낸다', async () => {
    const user = userEvent.setup()
    signIn()
    const fetchMock = mockApi({ brags: [brag({ username: 'jisu' })], me: 'jisu' })
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false)
    renderWithProviders(<BragPage />)

    await user.click(await screen.findByRole('button', { name: '이 글 삭제: 블랙빈 곤약국수' }))

    expect(confirmSpy).toHaveBeenCalled()
    const deletes = fetchMock.mock.calls.filter(
      ([, init]) => (init as RequestInit)?.method === 'DELETE',
    )
    expect(deletes).toHaveLength(0)
  })

  it('삭제를 확인하고 요청에 성공하면 피드에서 제거한다', async () => {
    const user = userEvent.setup()
    signIn()
    const fetchMock = mockApi({ brags: [brag({ username: 'jisu' })], me: 'jisu' })
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    renderWithProviders(<BragPage />)

    await user.click(await screen.findByRole('button', { name: '이 글 삭제: 블랙빈 곤약국수' }))

    expect(await screen.findByText(/아직 올라온 자랑이 없어요/)).toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([input, init]) => (
      new URL(input as string).pathname === '/brags/1' && init?.method === 'DELETE'
    ))).toBe(true)
    expect(screen.getByRole('button', { name: '사진 모아보기' })).toHaveFocus()
  })

  it('삭제 응답 대기 중 다른 글로 키보드 이동하면 초점을 피드 상단으로 옮기지 않는다', async () => {
    const user = userEvent.setup()
    signIn()
    let release!: (response: Response) => void
    mockApi({
      me: 'jisu',
      brags: [brag(), brag({ id: 2, username: '다른 사람', menu_name: '다음 요리' })],
      deleteResponse: () => new Promise((resolve) => { release = resolve }),
    })
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    renderWithProviders(<BragPage />)
    await user.click(await screen.findByRole('button', { name: '이 글 삭제: 블랙빈 곤약국수' }))
    await user.tab()
    const next = screen.getByRole('link', { name: '다음 요리 레시피 보기' })
    expect(next).toHaveFocus()

    await act(async () => { release(json({ deleted: true })) })
    expect(screen.queryByRole('button', { name: '이 글 삭제: 블랙빈 곤약국수' })).not.toBeInTheDocument()
    expect(next).toHaveFocus()
    expect(screen.getByRole('button', { name: '사진 모아보기' })).not.toHaveFocus()
  })

  it('아직 올라온 글이 없으면 그렇게 말한다', async () => {
    signIn()
    mockApi({ brags: [] })
    renderWithProviders(<BragPage />)

    expect(await screen.findByText(/아직 올라온 자랑이 없어요/)).toBeInTheDocument()
  })

  it('불러오기에 실패한 경우 글이 없다고 잘못 안내하지 않는다', async () => {
    signIn()
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const path = new URL(input as string).pathname
      if (path.startsWith('/profile/')) return json({ has_profile: true, username: 'me' })
      return json({ detail: '잠시 후 다시 시도해주세요.' }, 503)
    })
    renderWithProviders(<BragPage />)

    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(screen.queryByText(/아직 올라온 자랑이 없어요/)).not.toBeInTheDocument()
  })
})
