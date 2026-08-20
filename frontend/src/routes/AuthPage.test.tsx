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


/** 가입 화면이 쓸 선택지. 서버가 내려주므로 목록을 화면이 들고 있지 않다. */
const PROFILE_OPTIONS = {
  genders: ['여성', '남성', '선택 안 함'],
  age_groups: ['10대', '20대', '30대', '40대', '50대 이상'],
  medical_conditions: ['고혈압', '당뇨', '신장질환', '빈혈', '골다공증'],
  gender_undisclosed: '선택 안 함',
}

/**
 * 선택지 조회를 갈라내고 나머지는 주어진 응답으로 답한다.
 *
 * mockResolvedValue로 같은 Response를 돌려주면 안 된다 - 본문은 한 번만 읽히므로
 * 두 번째 요청이 빈 값을 받는다. 실제로 그렇게 깨진 적이 있다.
 */
function mockApi(body: unknown, status = 200) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    if (String(input).includes('/profile/options')) return jsonResponse(PROFILE_OPTIONS)
    return jsonResponse(body, status)
  })
}

/** 가입 요청만 센다. 화면이 선택지를 받아오므로 "fetch가 안 불렸다"로는 검사할 수 없다. */
function signupCalls(fetchMock: ReturnType<typeof mockApi>) {
  return fetchMock.mock.calls.filter(([url]) => String(url).includes('/auth/signup'))
}

async function fillAndSubmit(user: ReturnType<typeof userEvent.setup>, pw = 'pw123456') {
  await user.type(screen.getByLabelText('아이디'), 'jisu')
  await user.type(screen.getByLabelText('비밀번호'), pw)
  await user.click(screen.getByRole('button', { name: '로그인' }))
}

/** 가입 폼을 채운다. 검증하려는 항목만 옵션으로 비우거나 바꾼다. */
async function fillSignupForm(
  user: ReturnType<typeof userEvent.setup>,
  options: { skip?: string; email?: string; agreePrivacy?: boolean } = {},
) {
  const entries: [string, string][] = [
    ['아이디', 'newbie'],
    ['비밀번호', 'pw123456'],
    ['이름', '최지수'],
    ['연락처', '010-1234-5678'],
    ['이메일', options.email ?? 'newbie@example.com'],
  ]
  for (const [label, value] of entries) {
    if (options.skip === label) continue
    await user.type(screen.getByLabelText(label), value)
  }
  await user.selectOptions(screen.getByLabelText('성별'), '여성')
  await user.selectOptions(screen.getByLabelText('연령대'), '20대')

  await user.click(screen.getByLabelText(/이용약관/))
  if (options.agreePrivacy !== false) {
    await user.click(screen.getByLabelText(/개인정보/))
  }
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
    expect(signupCalls(fetchMock)).toHaveLength(0)
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
    const fetchMock = mockApi({ user_id: 42, token: 'tok-new' })
    renderWithProviders(<App />, { route: '/signup' })

    await fillSignupForm(user)
    await user.click(screen.getByRole('button', { name: '회원가입' }))

    await waitFor(() => {
      expect(screen.getByRole('heading', { level: 1, name: '오늘 뭐 먹지?' })).toBeInTheDocument()
    })
    expect(tokenStore.get()).toBe('tok-new')

    // 서버가 요구하는 항목이 실제로 실려 나가는지 본다. 폼만 보고 통과시키면
    // 필드를 화면에만 만들어두고 안 보내는 실수를 못 잡는다.
    // calls[0]은 선택지 조회다. 가입 요청을 골라서 본다.
    const sent = JSON.parse((signupCalls(fetchMock)[0][1] as RequestInit).body as string)
    expect(sent).toMatchObject({
      username: 'newbie',
      name: '최지수',
      phone: '010-1234-5678',
      email: 'newbie@example.com',
      gender: '여성',
      age_group: '20대',
      consents: { terms_of_service: true, privacy: true, marketing: false },
    })
  })

  it('필수 동의를 안 하면 서버에 보내지 않는다', async () => {
    // 콜드스타트가 30초라, 서버까지 보내고 거부당하면 30초를 버린다.
    const user = userEvent.setup()
    const fetchMock = mockApi({})
    renderWithProviders(<App />, { route: '/signup' })

    await fillSignupForm(user, { agreePrivacy: false })
    await user.click(screen.getByRole('button', { name: '회원가입' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('동의')
    expect(signupCalls(fetchMock)).toHaveLength(0)
  })

  it.each([
    ['이름', '이름을 입력해주세요.'],
    ['연락처', '연락처를 입력해주세요.'],
  ])('%s이(가) 비면 막는다', async (label, message) => {
    const user = userEvent.setup()
    const fetchMock = mockApi({})
    renderWithProviders(<App />, { route: '/signup' })

    await fillSignupForm(user, { skip: label })
    await user.click(screen.getByRole('button', { name: '회원가입' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(message)
    expect(signupCalls(fetchMock)).toHaveLength(0)
  })

  it('이메일 형식이 틀리면 막는다', async () => {
    const user = userEvent.setup()
    const fetchMock = mockApi({})
    renderWithProviders(<App />, { route: '/signup' })

    await fillSignupForm(user, { email: '골뱅이없음' })
    await user.click(screen.getByRole('button', { name: '회원가입' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('이메일 형식')
    expect(signupCalls(fetchMock)).toHaveLength(0)
  })

  it('로그인 화면에는 회원가입 전용 항목이 없다', () => {
    renderWithProviders(<App />, { route: '/login' })
    expect(screen.queryByLabelText('이메일')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('연락처')).not.toBeInTheDocument()
  })

  it('둘러보기 링크를 두지 않는다', () => {
    // 홈이 로그인 화면이 되면서 그 링크가 자기 자신을 가리키게 됐다(2026-08-20).
    // 로그인 없이 열리는 것은 공유받은 레시피 상세 하나뿐이고, 그건 여기서 갈 곳이 아니다.
    renderWithProviders(<App />, { route: '/login' })

    expect(screen.queryByRole('link', { name: '로그인 없이 둘러보기' })).not.toBeInTheDocument()
    expect(tokenStore.get()).toBeNull()
  })
})
