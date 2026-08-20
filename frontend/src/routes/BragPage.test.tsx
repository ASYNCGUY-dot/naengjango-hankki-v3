import { screen, waitFor } from '@testing-library/react'
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
function mockApi(options: { brags?: unknown[]; me?: string; likeFails?: boolean } = {}) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const path = new URL(input as string).pathname
    if ((init as RequestInit | undefined)?.method === 'POST') {
      if (options.likeFails) return json({ detail: '오류' }, 500)
      return json({ liked: true, like_count: 3 })
    }
    if ((init as RequestInit | undefined)?.method === 'DELETE') return json({ deleted: true })
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
    expect(screen.getByRole('link', { name: /블랙빈 곤약국수 레시피 보기/ })).toHaveAttribute(
      'href',
      '/recipe/67',
    )
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
    await waitFor(() => expect(screen.getAllByRole('button', { name: '삭제' })).toHaveLength(1))
  })

  it('삭제는 확인을 받고 나서만 보낸다', async () => {
    const user = userEvent.setup()
    signIn()
    const fetchMock = mockApi({ brags: [brag({ username: 'jisu' })], me: 'jisu' })
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false)
    renderWithProviders(<BragPage />)

    await user.click(await screen.findByRole('button', { name: '삭제' }))

    expect(confirmSpy).toHaveBeenCalled()
    const deletes = fetchMock.mock.calls.filter(
      ([, init]) => (init as RequestInit)?.method === 'DELETE',
    )
    expect(deletes).toHaveLength(0)
  })

  it('아직 올라온 글이 없으면 그렇게 말한다', async () => {
    signIn()
    mockApi({ brags: [] })
    renderWithProviders(<BragPage />)

    expect(await screen.findByText(/아직 올라온 자랑이 없어요/)).toBeInTheDocument()
  })
})
