import { act, fireEvent, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from '../App'
import { tokenStore } from '../api/client'
import { renderWithProviders } from '../test/renderWithProviders'

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

async function fillAndSubmit(user: ReturnType<typeof userEvent.setup>, pw = 'pw123456') {
  await user.type(screen.getByLabelText('아이디'), 'jisu')
  await user.type(screen.getByLabelText('비밀번호'), pw)
  await user.click(screen.getByRole('button', { name: '로그인' }))
}

describe('로그인 화면', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.useRealTimers()
  })

  it('로그인에 성공하면 토큰을 저장하고 홈으로 보낸다', async () => {
    const user = userEvent.setup()
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse({ user_id: 15, token: 'tok-abc' }),
    )
    renderWithProviders(<App />, { route: '/login' })

    await fillAndSubmit(user)

    await waitFor(() => {
      expect(screen.getByRole('heading', { level: 1, name: '오늘 뭐 먹지?' })).toBeInTheDocument()
    })
    expect(tokenStore.get()).toBe('tok-abc')
  })

  it('아이디나 비밀번호가 틀리면 백엔드 문구를 그대로 보여준다', async () => {
    const user = userEvent.setup()
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse({ detail: '아이디 또는 비밀번호가 올바르지 않습니다.' }, 401),
    )
    renderWithProviders(<App />, { route: '/login' })

    await fillAndSubmit(user)

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('아이디 또는 비밀번호가 올바르지 않습니다.')
    // 실패했으면 화면이 그대로여야 한다.
    expect(screen.getByRole('button', { name: '로그인' })).toBeInTheDocument()
  })

  it('짧은 비밀번호는 서버에 보내기 전에 막는다', async () => {
    // 콜드스타트가 30초라, 이걸 서버까지 보내면 30초를 기다린 끝에 "짧습니다"를 본다.
    const user = userEvent.setup()
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse({}))
    renderWithProviders(<App />, { route: '/login' })

    await fillAndSubmit(user, 'short')

    expect(await screen.findByRole('alert')).toHaveTextContent('8자 이상')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('요청이 진행되는 동안 버튼을 잠근다', async () => {
    const user = userEvent.setup()
    let release: (value: Response) => void = () => {}
    vi.spyOn(globalThis, 'fetch').mockReturnValue(
      new Promise<Response>((resolve) => {
        release = resolve
      }),
    )
    renderWithProviders(<App />, { route: '/login' })

    await fillAndSubmit(user)

    // 두 번 눌러서 요청이 두 번 나가는 것을 막는다.
    const button = screen.getByRole('button', { name: '로그인 중…' })
    expect(button).toBeDisabled()

    release(jsonResponse({ user_id: 15, token: 'tok' }))
  })

  it('응답이 느리면 서버를 깨우는 중이라고 알린다', async () => {
    // Render 무료 티어는 첫 요청이 30초 넘게 걸린다(실측 34.6초). 아무 신호가 없으면
    // 사용자는 앱이 멈춘 줄 안다.
    // 여기서는 userEvent를 쓰지 않는다. userEvent의 타이핑은 내부적으로 타이머를 쓰는데
    // 가짜 타이머와 얽히면 테스트가 멈춘다. 입력을 동기 이벤트로 바로 넣는다.
    vi.useFakeTimers()
    vi.spyOn(globalThis, 'fetch').mockReturnValue(new Promise<Response>(() => {}))
    renderWithProviders(<App />, { route: '/login' })

    fireEvent.change(screen.getByLabelText('아이디'), { target: { value: 'jisu' } })
    fireEvent.change(screen.getByLabelText('비밀번호'), { target: { value: 'pw123456' } })
    fireEvent.click(screen.getByRole('button', { name: '로그인' }))

    // 서버가 깨어 있으면 1초 안에 끝난다. 그때 안내가 깜빡이면 오히려 느려 보인다.
    expect(screen.queryByRole('status')).not.toBeInTheDocument()

    await act(async () => {
      await vi.advanceTimersByTimeAsync(3_500)
    })
    expect(screen.getByRole('status')).toHaveTextContent('서버를 깨우는 중')
  })

  it('회원가입 화면은 가입 후 바로 로그인 상태가 된다', async () => {
    const user = userEvent.setup()
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse({ user_id: 42, token: 'tok-new' }),
    )
    renderWithProviders(<App />, { route: '/signup' })

    await user.type(screen.getByLabelText('아이디'), 'newbie')
    await user.type(screen.getByLabelText('비밀번호'), 'pw123456')
    await user.click(screen.getByRole('button', { name: '회원가입' }))

    await waitFor(() => {
      expect(screen.getByRole('heading', { level: 1, name: '오늘 뭐 먹지?' })).toBeInTheDocument()
    })
    expect(tokenStore.get()).toBe('tok-new')
  })

  it('로그인 없이 둘러보기로 홈에 갈 수 있다', async () => {
    const user = userEvent.setup()
    renderWithProviders(<App />, { route: '/login' })

    await user.click(screen.getByRole('link', { name: '로그인 없이 둘러보기' }))

    expect(screen.getByRole('heading', { level: 1, name: '오늘 뭐 먹지?' })).toBeInTheDocument()
    expect(tokenStore.get()).toBeNull()
  })
})
