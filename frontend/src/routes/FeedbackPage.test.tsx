import { act, screen, waitFor, within } from '@testing-library/react'
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
  options: {
    mine?: unknown[]
    all?: unknown[]
    isAdmin?: boolean
    postFails?: boolean
    postResponse?: () => Response | Promise<Response>
    mineResponse?: () => Response | Promise<Response>
    allResponse?: () => Response | Promise<Response>
    profileResponse?: () => Response | Promise<Response>
    deleteResponse?: () => Response | Promise<Response>
  } = {},
) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const path = new URL(input as string).pathname
    const method = (init as RequestInit | undefined)?.method
    if (method === 'POST') {
      if (options.postResponse) return options.postResponse()
      if (options.postFails) return json({ detail: '서버에서 문제가 발생했습니다.' }, 500)
      const sent = JSON.parse((init as RequestInit).body as string)
      return json(item({ id: 99, body: sent.body }))
    }
    if (method === 'DELETE') return options.deleteResponse?.() ?? json({ deleted: true })
    if (path.startsWith('/profile/')) {
      if (options.profileResponse) return options.profileResponse()
      return json({ has_profile: true, username: 'me', is_admin: options.isAdmin ?? false })
    }
    if (path === '/feedback/all') {
      // 관리자가 아니면 서버가 막는다.
      if (!options.isAdmin) return json({ detail: '관리자 권한이 없습니다.' }, 403)
      return options.allResponse?.() ?? json(options.all ?? [])
    }
    return options.mineResponse?.() ?? json(options.mine ?? [])
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

  it.each(['', '   '])('빈 내용(%j)은 보내지 않고 오류를 알려 입력칸으로 초점을 옮긴다', async (body) => {
    const user = userEvent.setup()
    signIn()
    const fetchMock = mockApi()
    renderWithProviders(<FeedbackPage />)

    const input = screen.getByLabelText('이런 게 궁금해요')
    if (body) await user.type(input, body)
    const button = await screen.findByRole('button', { name: '보내기' })
    expect(button).toBeEnabled()
    await user.click(button)

    expect(await screen.findByRole('alert')).toHaveTextContent('보낼 의견을 입력해주세요.')
    expect(input).toHaveFocus()
    expect(input).toHaveAttribute('aria-invalid', 'true')
    expect(input).toHaveAccessibleDescription('보낼 의견을 입력해주세요.')
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(0)

    await user.type(input, '의견을 적었어요')
    expect(input).toHaveAttribute('aria-invalid', 'false')
    expect(screen.queryByText('보낼 의견을 입력해주세요.')).not.toBeInTheDocument()
  })

  it('보내는 동안 중복 제출을 막고 완료 후 다시 보낼 수 있다', async () => {
    const user = userEvent.setup()
    signIn()
    let resolvePost!: (response: Response) => void
    const fetchMock = mockApi({ postResponse: () => new Promise((resolve) => { resolvePost = resolve }) })
    renderWithProviders(<FeedbackPage />)

    const input = screen.getByLabelText('이런 게 궁금해요')
    await user.type(input, '재료비가 보기 편해요')
    await user.dblClick(screen.getByRole('button', { name: '보내기' }))

    expect(screen.getByRole('button', { name: '보내는 중…' })).toBeDisabled()
    expect(input.closest('form')).toHaveAttribute('aria-busy', 'true')
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(1)

    await act(async () => { resolvePost(json(item({ id: 99, body: '재료비가 보기 편해요' }))) })
    expect(screen.getByRole('button', { name: '보내기' })).toBeEnabled()
    expect(input.closest('form')).toHaveAttribute('aria-busy', 'false')
  })

  it('보내면 목록 맨 위에 붙고 입력칸을 비운다', async () => {
    const user = userEvent.setup()
    signIn()
    mockApi()
    renderWithProviders(<FeedbackPage />)

    await user.type(await screen.findByLabelText(/이런 게 궁금해요/), '추천이 좀 뻔했어요')
    await user.click(screen.getByRole('button', { name: '보내기' }))

    expect(await screen.findByText('추천이 좀 뻔했어요')).toBeInTheDocument()
    expect(screen.getByText('고맙습니다. 잘 읽을게요.')).toHaveAttribute('role', 'status')
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

    await user.click(await screen.findByRole('button', { name: /재료 넣는 게 좀 귀찮았어요.*지우기/ }))

    expect(confirmSpy).toHaveBeenCalled()
    const deletes = fetchMock.mock.calls.filter(
      ([, init]) => (init as RequestInit)?.method === 'DELETE',
    )
    expect(deletes).toHaveLength(0)
  })

  it('목록을 기다리는 동안 빈 결과를 미리 표시하지 않는다', async () => {
    signIn()
    let resolveMine!: (response: Response) => void
    mockApi({ mineResponse: () => new Promise((resolve) => { resolveMine = resolve }) })
    renderWithProviders(<FeedbackPage />)

    expect(screen.getByText('내가 보낸 말을 불러오는 중이에요.')).toHaveAttribute('role', 'status')
    expect(screen.queryByText('아직 없어요.')).not.toBeInTheDocument()

    await act(async () => { resolveMine(json([])) })
    expect(await screen.findByText('아직 없어요.')).toBeInTheDocument()
    expect(screen.queryByText('내가 보낸 말을 불러오는 중이에요.')).not.toBeInTheDocument()
  })

  it('내 목록 조회 실패를 빈 결과와 구분하고 재시도 뒤 제목으로 초점을 돌린다', async () => {
    const user = userEvent.setup()
    signIn()
    let attempts = 0
    mockApi({ mineResponse: () => ++attempts === 1
      ? json({ detail: '내 의견을 조회하지 못했습니다.' }, 500)
      : json([item()]) })
    renderWithProviders(<FeedbackPage />)

    expect(await screen.findByRole('alert')).toHaveTextContent('내 의견을 조회하지 못했습니다.')
    expect(screen.queryByText('아직 없어요.')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '내 의견 다시 불러오기' }))

    expect(await screen.findByText('재료 넣는 게 좀 귀찮았어요.')).toBeInTheDocument()
    expect(attempts).toBe(2)
    expect(screen.getByRole('heading', { name: '내가 보낸 말' })).toHaveFocus()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('관리자의 전체 목록 조회가 실패하면 이유와 다시 확인할 버튼을 보여준다', async () => {
    const user = userEvent.setup()
    signIn()
    let attempts = 0
    mockApi({
      isAdmin: true,
      allResponse: () => ++attempts === 1
        ? json({ detail: '전체 의견을 조회하지 못했습니다.' }, 500)
        : json([item({ id: 2, body: '다른 사람 의견', username: '작성자' })]),
    })
    renderWithProviders(<FeedbackPage />)

    expect(await screen.findByRole('alert')).toHaveTextContent('전체 의견을 조회하지 못했습니다.')
    await user.click(screen.getByRole('button', { name: '전체 의견 다시 확인하기' }))

    expect(await screen.findByText('다른 사람 의견')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '전체 의견 (1)' })).toHaveFocus()
  })

  it('권한 조회 실패를 숨기지 않고 일반 계정 재확인 뒤 전체 목록을 요청하지 않는다', async () => {
    const user = userEvent.setup()
    signIn()
    let attempts = 0
    const fetchMock = mockApi({
      profileResponse: () => ++attempts === 1
        ? json({ detail: '일시적인 오류' }, 500)
        : json({ is_admin: false }),
    })
    renderWithProviders(<FeedbackPage />)

    expect(await screen.findByRole('alert')).toHaveTextContent('계정 권한을 확인하지 못했어요.')
    await user.click(screen.getByRole('button', { name: '전체 의견 다시 확인하기' }))
    await waitFor(() => expect(screen.queryByRole('heading', { name: '계정 권한 확인' })).not.toBeInTheDocument())
    expect(screen.getByLabelText('이런 게 궁금해요')).toHaveFocus()
    expect(fetchMock.mock.calls.some(([input]) => new URL(input as string).pathname === '/feedback/all')).toBe(false)
  })

  it('삭제 중 중복 요청을 막고 다음 의견과 마지막 삭제 후 입력란으로 초점을 돌린다', async () => {
    const user = userEvent.setup()
    signIn()
    let resolveDelete!: (response: Response) => void
    const fetchMock = mockApi({
      mine: [item({ id: 1, body: '첫 번째 의견' }), item({ id: 2, body: '두 번째 의견' })],
      deleteResponse: () => new Promise((resolve) => { resolveDelete = resolve }),
    })
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    renderWithProviders(<FeedbackPage />)

    const first = await screen.findByRole('button', { name: '1번째 의견: 첫 번째 의견 지우기' })
    await user.click(first)
    expect(first).toBeDisabled()
    expect(first).toHaveTextContent('지우는 중…')
    first.click()
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === 'DELETE')).toHaveLength(1)

    await act(async () => { resolveDelete(json({ deleted: true })) })
    const next = screen.getByRole('button', { name: '1번째 의견: 두 번째 의견 지우기' })
    expect(next).toHaveFocus()
    expect(screen.getByText('의견을 지웠어요.')).toHaveAttribute('role', 'status')
    await user.click(next)
    await act(async () => { resolveDelete(json({ deleted: true })) })
    expect(screen.getByLabelText('이런 게 궁금해요')).toHaveFocus()
    expect(screen.getByText('아직 없어요.')).toBeInTheDocument()
  })

  it('삭제 실패 시 의견을 남겨두고 해당 삭제 버튼으로 초점을 복원한다', async () => {
    const user = userEvent.setup()
    signIn()
    mockApi({
      mine: [item()],
      deleteResponse: () => json({ detail: '삭제에 실패했습니다.' }, 500),
    })
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    renderWithProviders(<FeedbackPage />)

    const button = await screen.findByRole('button', { name: /재료 넣는 게 좀 귀찮았어요.*지우기/ })
    await user.click(button)
    expect(await screen.findByRole('alert')).toHaveTextContent('삭제에 실패했습니다.')
    expect(screen.getByText('재료 넣는 게 좀 귀찮았어요.')).toBeInTheDocument()
    expect(button).toBeEnabled()
    expect(button).toHaveFocus()
    expect(screen.queryByText('의견을 지웠어요.')).not.toBeInTheDocument()
  })

  it('관리자가 본인 의견을 지우면 전체 목록에서도 제거한다', async () => {
    const user = userEvent.setup()
    signIn()
    mockApi({ isAdmin: true, mine: [item()], all: [item()] })
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    renderWithProviders(<FeedbackPage />)
    await screen.findByRole('heading', { name: '전체 의견 (1)' })

    await user.click(screen.getByRole('button', { name: /재료 넣는 게 좀 귀찮았어요.*지우기/ }))
    const allSection = await screen.findByRole('region', { name: '전체 의견 (0)' })
    expect(within(allSection).queryByText('재료 넣는 게 좀 귀찮았어요.')).not.toBeInTheDocument()
    expect(within(allSection).getByText('아직 등록된 의견이 없어요.')).toBeInTheDocument()
  })

  it('느린 목록 응답이 방금 보낸 의견을 지우지 않는다', async () => {
    const user = userEvent.setup()
    signIn()
    let resolveMine!: (response: Response) => void
    mockApi({ mineResponse: () => new Promise((resolve) => { resolveMine = resolve }) })
    renderWithProviders(<FeedbackPage />)

    await user.type(screen.getByLabelText('이런 게 궁금해요'), '새로 쓴 의견')
    await user.click(screen.getByRole('button', { name: '보내기' }))
    await screen.findByText('새로 쓴 의견')
    await act(async () => { resolveMine(json([item()])) })
    expect(screen.getByText('새로 쓴 의견')).toBeInTheDocument()
    expect(screen.getByText('재료 넣는 게 좀 귀찮았어요.')).toBeInTheDocument()
  })

  it('목록을 다시 불러오는 동안 입력을 시작하면 완료 뒤에도 입력 초점을 유지한다', async () => {
    const user = userEvent.setup()
    signIn()
    let attempts = 0
    let resolveMine!: (response: Response) => void
    mockApi({
      mineResponse: () => ++attempts === 1
        ? json({ detail: '조회 실패' }, 500)
        : new Promise((resolve) => { resolveMine = resolve }),
    })
    renderWithProviders(<FeedbackPage />)

    await user.click(await screen.findByRole('button', { name: '내 의견 다시 불러오기' }))
    const input = screen.getByLabelText('이런 게 궁금해요')
    await user.type(input, '계속 입력하는 중')
    await act(async () => { resolveMine(json([item()])) })

    expect(input).toHaveFocus()
    expect(input).toHaveValue('계속 입력하는 중')
    expect(screen.getByRole('heading', { name: '내가 보낸 말' })).not.toHaveFocus()
  })

  it('삭제 응답을 기다리는 동안 다른 입력으로 이동하면 완료 뒤 초점을 빼앗지 않는다', async () => {
    const user = userEvent.setup()
    signIn()
    let resolveDelete!: (response: Response) => void
    mockApi({
      mine: [item(), item({ id: 2, body: '남겨둘 의견' })],
      deleteResponse: () => new Promise((resolve) => { resolveDelete = resolve }),
    })
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    renderWithProviders(<FeedbackPage />)

    await user.click(await screen.findByRole('button', { name: /재료 넣는 게 좀 귀찮았어요.*지우기/ }))
    const input = screen.getByLabelText('이런 게 궁금해요')
    await user.type(input, '삭제를 기다리며 입력')
    await act(async () => { resolveDelete(json({ deleted: true })) })

    expect(screen.queryByText('재료 넣는 게 좀 귀찮았어요.')).not.toBeInTheDocument()
    expect(screen.getByText('의견을 지웠어요.')).toBeInTheDocument()
    expect(input).toHaveFocus()
    expect(screen.getByRole('button', { name: /남겨둘 의견 지우기/ })).not.toHaveFocus()
  })
})
