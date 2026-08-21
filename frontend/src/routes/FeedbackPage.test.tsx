import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import FeedbackPage from './FeedbackPage'
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
    id: 1,
    body: '재료 넣는 게 좀 귀찮았어요.',
    created_at: '2026-08-22T09:30:00',
    username: null,
    ...overrides,
  }
}

/** 프로필·본인목록·전체목록·작성을 경로와 method로 갈라 답한다. */
function mockApi(
  options: { mine?: unknown[]; all?: unknown[]; isAdmin?: boolean; postFails?: boolean } = {},
) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const path = new URL(input as string).pathname
    const method = (init as RequestInit | undefined)?.method
    if (method === 'POST') {
      if (options.postFails) return json({ detail: '서버에서 문제가 발생했습니다.' }, 500)
      const sent = JSON.parse((init as RequestInit).body as string)
      return json(item({ id: 99, body: sent.body }))
    }
    if (method === 'DELETE') return json({ deleted: true })
    if (path.startsWith('/profile/')) {
      return json({ has_profile: true, username: 'me', is_admin: options.isAdmin ?? false })
    }
    if (path === '/feedback/all') {
      // 관리자가 아니면 서버가 막는다.
      if (!options.isAdmin) return json({ detail: '관리자 권한이 없습니다.' }, 403)
      return json(options.all ?? [])
    }
    return json(options.mine ?? [])
  })
}

describe('하고 싶은 말', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.restoreAllMocks())

  it('로그인하지 않으면 아무 요청도 보내지 않는다', () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
    renderWithProviders(<FeedbackPage />)

    expect(screen.getByRole('link', { name: '로그인하러 가기' })).toHaveAttribute('href', '/login')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('다른 사람에게는 안 보인다고 미리 알린다', async () => {
    // 안 적으면 솔직하게 안 쓴다. 이 기능은 솔직한 말을 받으려고 있는 것이다.
    signIn()
    mockApi()
    renderWithProviders(<FeedbackPage />)

    expect(await screen.findByText(/만든 사람만 읽고, 다른 사람에게는 안 보여요/)).toBeInTheDocument()
  })

  it('무엇을 적어야 할지 예시를 준다', async () => {
    // 빈 칸만 있으면 아무도 안 쓴다. 초대 페이지에서 물은 것과 같은 넷이다.
    signIn()
    mockApi()
    renderWithProviders(<FeedbackPage />)

    expect(await screen.findByText(/어디서 “뭐 어쩌라는 거지” 싶었는지/)).toBeInTheDocument()
    expect(screen.getByText(/안 쓰게 됐다면 며칠째에 그랬는지/)).toBeInTheDocument()
  })

  it('빈 내용으로는 보낼 수 없다', async () => {
    signIn()
    mockApi()
    renderWithProviders(<FeedbackPage />)

    expect(await screen.findByRole('button', { name: '보내기' })).toBeDisabled()
  })

  it('보내면 목록 맨 위에 붙고 입력칸을 비운다', async () => {
    const user = userEvent.setup()
    signIn()
    mockApi()
    renderWithProviders(<FeedbackPage />)

    await user.type(await screen.findByLabelText(/이런 게 궁금해요/), '추천이 좀 뻔했어요')
    await user.click(screen.getByRole('button', { name: '보내기' }))

    expect(await screen.findByText('추천이 좀 뻔했어요')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('고맙습니다')
    // 안 비우면 같은 말을 두 번 보내기 쉽다.
    await waitFor(() => expect(screen.getByLabelText(/이런 게 궁금해요/)).toHaveValue(''))
  })

  it('실패하면 알리고 쓴 내용을 지우지 않는다', async () => {
    const user = userEvent.setup()
    signIn()
    mockApi({ postFails: true })
    renderWithProviders(<FeedbackPage />)

    await user.type(await screen.findByLabelText(/이런 게 궁금해요/), '살아남아야 하는 글')
    await user.click(screen.getByRole('button', { name: '보내기' }))

    // 서버가 준 이유를 그대로 보여준다. 화면이 지어낸 문구로 덮으면 원인을 알 수 없다.
    expect(await screen.findByRole('alert')).toHaveTextContent('서버에서 문제가 발생했습니다')
    expect(screen.getByLabelText(/이런 게 궁금해요/)).toHaveValue('살아남아야 하는 글')
  })

  it('일반 계정에게는 전체 목록을 보여주지 않는다', async () => {
    // 남의 의견이 보이면 그쪽으로 끌려가서 "나도 그랬어"를 쓰게 된다.
    signIn()
    mockApi({ mine: [item()], all: [item({ id: 2, body: '남의 의견', username: '남' })] })
    renderWithProviders(<FeedbackPage />)

    await screen.findByText('재료 넣는 게 좀 귀찮았어요.')
    expect(screen.queryByText('남의 의견')).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /전체/ })).not.toBeInTheDocument()
  })

  it('관리자에게는 누가 썼는지와 함께 전체를 보여준다', async () => {
    signIn()
    mockApi({
      isAdmin: true,
      mine: [],
      all: [item({ id: 2, body: '남의 의견', username: '지인1' })],
    })
    renderWithProviders(<FeedbackPage />)

    expect(await screen.findByText('남의 의견')).toBeInTheDocument()
    expect(screen.getByText('지인1')).toBeInTheDocument()
  })

  it('지우기는 확인을 받고 나서만 보낸다', async () => {
    const user = userEvent.setup()
    signIn()
    const fetchMock = mockApi({ mine: [item()] })
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false)
    renderWithProviders(<FeedbackPage />)

    await user.click(await screen.findByRole('button', { name: '지우기' }))

    expect(confirmSpy).toHaveBeenCalled()
    const deletes = fetchMock.mock.calls.filter(
      ([, init]) => (init as RequestInit)?.method === 'DELETE',
    )
    expect(deletes).toHaveLength(0)
  })
})