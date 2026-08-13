import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from '../App'
import { renderWithProviders } from '../test/renderWithProviders'

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('비밀번호 초기화 요청', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.restoreAllMocks())

  it('요청하면 "가입된 이메일이라면"이라고 안내한다', async () => {
    // 서버는 가입된 주소든 아니든 같은 응답을 준다(계정 존재 여부를 숨기기 위해).
    // 화면이 "보냈습니다"라고 단정하면 사실과 다르고, 없는 주소를 넣은 사람은
    // 오지 않는 메일을 기다리게 된다.
    const user = userEvent.setup()
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse({ requested: true }))
    renderWithProviders(<App />, { route: '/forgot-password' })

    await user.type(screen.getByLabelText('이메일'), 'someone@example.com')
    await user.click(screen.getByRole('button', { name: '초기화 링크 받기' }))

    const status = await screen.findByRole('status')
    expect(status).toHaveTextContent('가입된 이메일이라면')
  })

  it('로그인 화면에서 초기화로 갈 수 있다', async () => {
    const user = userEvent.setup()
    renderWithProviders(<App />, { route: '/login' })

    await user.click(screen.getByRole('link', { name: '비밀번호를 잊으셨나요?' }))

    expect(screen.getByRole('heading', { level: 1, name: '비밀번호 초기화' })).toBeInTheDocument()
  })
})

describe('새 비밀번호 설정', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.restoreAllMocks())

  it('토큰 없이 들어오면 링크가 잘못됐다고 알린다', () => {
    renderWithProviders(<App />, { route: '/reset-password' })
    expect(screen.getByRole('alert')).toHaveTextContent('링크가 올바르지 않습니다')
  })

  it('두 비밀번호가 다르면 서버에 보내지 않는다', async () => {
    const user = userEvent.setup()
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse({}))
    renderWithProviders(<App />, { route: '/reset-password?token=abc' })

    await user.type(screen.getByLabelText('새 비밀번호'), 'pw123456')
    await user.type(screen.getByLabelText('새 비밀번호 확인'), 'pw999999')
    await user.click(screen.getByRole('button', { name: '비밀번호 변경' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('두 비밀번호가 다릅니다')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('짧은 비밀번호는 서버에 보내지 않는다', async () => {
    const user = userEvent.setup()
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse({}))
    renderWithProviders(<App />, { route: '/reset-password?token=abc' })

    await user.type(screen.getByLabelText('새 비밀번호'), 'short')
    await user.type(screen.getByLabelText('새 비밀번호 확인'), 'short')
    await user.click(screen.getByRole('button', { name: '비밀번호 변경' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('8자 이상')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('성공하면 다른 기기 로그인도 풀렸다고 알린다', async () => {
    // 백엔드가 초기화 시 auth_tokens를 지운다. 사용자가 그걸 모르면 다른 기기에서
    // 갑자기 로그아웃된 이유를 알 수 없다.
    const user = userEvent.setup()
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(jsonResponse({ reset: true, detail: '비밀번호가 변경되었습니다.' }))
    renderWithProviders(<App />, { route: '/reset-password?token=tok-abc' })

    await user.type(screen.getByLabelText('새 비밀번호'), 'newpw12345')
    await user.type(screen.getByLabelText('새 비밀번호 확인'), 'newpw12345')
    await user.click(screen.getByRole('button', { name: '비밀번호 변경' }))

    const status = await screen.findByRole('status')
    expect(status).toHaveTextContent('비밀번호가 바뀌었어요')
    expect(status).toHaveTextContent('다른 기기에 남아 있던 로그인도 함께 해제')

    const sent = JSON.parse((fetchMock.mock.calls[0][1] as RequestInit).body as string)
    expect(sent).toEqual({ token: 'tok-abc', new_password: 'newpw12345' })
  })

  it('만료된 링크면 서버 문구를 그대로 보여준다', async () => {
    const user = userEvent.setup()
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse({ detail: '만료된 링크입니다. 초기화를 다시 요청해주세요.' }, 400),
    )
    renderWithProviders(<App />, { route: '/reset-password?token=expired' })

    await user.type(screen.getByLabelText('새 비밀번호'), 'newpw12345')
    await user.type(screen.getByLabelText('새 비밀번호 확인'), 'newpw12345')
    await user.click(screen.getByRole('button', { name: '비밀번호 변경' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('만료된 링크')
  })

  it('변경 후 로그인 화면으로 갈 수 있다', async () => {
    const user = userEvent.setup()
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse({ reset: true }))
    renderWithProviders(<App />, { route: '/reset-password?token=tok' })

    await user.type(screen.getByLabelText('새 비밀번호'), 'newpw12345')
    await user.type(screen.getByLabelText('새 비밀번호 확인'), 'newpw12345')
    await user.click(screen.getByRole('button', { name: '비밀번호 변경' }))

    await user.click(await screen.findByRole('button', { name: '로그인하러 가기' }))

    await waitFor(() => {
      expect(screen.getByRole('button', { name: '로그인' })).toBeInTheDocument()
    })
  })
})
