import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import OnboardingPage from './OnboardingPage'
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

const PROFILE_OPTIONS = {
  genders: ['여성', '남성', '선택 안 함'],
  age_groups: ['10대', '20대', '30대', '40대', '50대 이상'],
  medical_conditions: ['고혈압', '당뇨', '신장질환', '빈혈', '골다공증'],
  gender_undisclosed: '선택 안 함',
}

const ALLERGY_OPTIONS = [
  { value: '달걀', label: '달걀', recipe_count: 227 },
  { value: '우유', label: '우유', recipe_count: 88 },
  { value: '대두', label: '대두', recipe_count: 41 },
]

function profile(overrides: Record<string, unknown> = {}) {
  return {
    has_profile: false,
    username: 'jisu',
    name: '최지수',
    gender: '여성',
    age_group: '20대',
    allergy: null,
    health_goal: null,
    purpose: null,
    cooking_level: null,
    supplements: null,
    household_size: null,
    novelty_pref: null,
    cooking_tools: null,
    medical_conditions: null,
    ...overrides,
  }
}

/** 두 GET(프로필·알레르기 목록)을 주소로 갈라 응답한다. */
function mockApi(options: {
  profile?: Record<string, unknown>
  allergyOptions?: unknown
  profileStatus?: number
  allergyStatus?: number
  putStatus?: number
}) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    if ((init as RequestInit | undefined)?.method === 'PUT') {
      return json({ updated: true }, options.putStatus ?? 200)
    }
    if (url.includes('/profile/options')) {
      return json(PROFILE_OPTIONS)
    }
    if (url.includes('/profile/allergy-options')) {
      return json(options.allergyOptions ?? ALLERGY_OPTIONS, options.allergyStatus ?? 200)
    }
    return json(options.profile ?? profile(), options.profileStatus ?? 200)
  })
}

/** 필수 선택 네 개를 채운다 - 이걸 안 채우면 저장 자체가 막힌다. */
async function fillRequired(user: ReturnType<typeof userEvent.setup>) {
  await user.selectOptions(screen.getByLabelText('건강목표'), '체중감량')
  await user.selectOptions(screen.getByLabelText('이용목적'), '간단한 한 끼')
  await user.selectOptions(screen.getByLabelText('요리수준'), '초급')
  await user.selectOptions(screen.getByLabelText('메뉴취향'), '새로운 메뉴 선호')
}

function putBody(fetchMock: ReturnType<typeof mockApi>): Record<string, unknown> {
  const call = fetchMock.mock.calls.find(
    ([, init]) => (init as RequestInit | undefined)?.method === 'PUT',
  )
  if (call === undefined) throw new Error('PUT 요청이 없다')
  return JSON.parse(String((call[1] as RequestInit).body)) as Record<string, unknown>
}

describe('식단 정보 입력', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.restoreAllMocks())

  it('로그인하지 않으면 아무것도 부르지 않고 로그인으로 안내한다', () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
    renderWithProviders(<OnboardingPage />)

    expect(screen.getByRole('link', { name: '로그인하러 가기' })).toHaveAttribute('href', '/login')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('알레르기 선택지는 서버가 준 목록에서만 나온다', async () => {
    // 화면이 목록을 지어내면 태그에 없는 값("콩" 같은)이 저장되고, 사용자는 걸렀다고
    // 믿는데 필터는 아무것도 안 거른다.
    signIn()
    mockApi({ allergyOptions: [{ value: '메밀', label: '메밀', recipe_count: 3 }] })
    renderWithProviders(<OnboardingPage />)

    expect(await screen.findByRole('button', { name: '메밀' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '달걀' })).not.toBeInTheDocument()
  })

  it('고른 알레르기를 콤마로 이어 저장한다', async () => {
    const user = userEvent.setup()
    signIn()
    const fetchMock = mockApi({})
    renderWithProviders(<OnboardingPage />)

    await user.click(await screen.findByRole('button', { name: '달걀' }))
    await user.click(screen.getByRole('button', { name: '대두' }))
    await user.click(screen.getByLabelText(/알레르기·병력 정보 수집에 동의/))
    await fillRequired(user)
    await user.click(screen.getByRole('button', { name: '저장하기' }))

    await waitFor(() => expect(putBody(fetchMock).allergy).toBe('달걀,대두'))
  })

  it('가입 때 받은 성별·연령대를 그대로 실어 보낸다', async () => {
    // PUT은 프로필 전체를 덮어쓴다. 화면이 안 묻는다고 빼고 보내면 가입 때 받은 값이
    // 빈 문자열로 날아간다.
    const user = userEvent.setup()
    signIn()
    const fetchMock = mockApi({})
    renderWithProviders(<OnboardingPage />)

    await screen.findByRole('button', { name: '달걀' })
    await fillRequired(user)
    await user.click(screen.getByRole('button', { name: '저장하기' }))

    await waitFor(() => {
      const body = putBody(fetchMock)
      expect(body.gender).toBe('여성')
      expect(body.age_group).toBe('20대')
    })
  })

  it('필수 항목을 안 고르면 저장 요청을 보내지 않는다', async () => {
    const user = userEvent.setup()
    signIn()
    const fetchMock = mockApi({})
    renderWithProviders(<OnboardingPage />)

    await user.click(await screen.findByRole('button', { name: '달걀' }))
    await user.click(screen.getByRole('button', { name: '저장하기' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('건강목표')
    expect(
      fetchMock.mock.calls.some(([, init]) => (init as RequestInit | undefined)?.method === 'PUT'),
    ).toBe(false)
  })

  it('이미 입력한 값이 있으면 채워둔다', async () => {
    signIn()
    mockApi({
      profile: profile({
        has_profile: true,
        allergy: '우유',
        health_goal: '근육증가',
        household_size: 3,
        cooking_tools: '에어프라이어',
      }),
    })
    renderWithProviders(<OnboardingPage />)

    await waitFor(() =>
      expect(screen.getByRole('button', { name: '우유' })).toHaveAttribute('aria-pressed', 'true'),
    )
    expect(screen.getByRole('button', { name: '달걀' })).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByRole('button', { name: '에어프라이어' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    expect(screen.getByLabelText('건강목표')).toHaveValue('근육증가')
    expect(screen.getByLabelText('가구원 수')).toHaveValue('3')
  })

  it('건강 정보를 넣으면 별도 동의를 묻는다', async () => {
    // 알레르기·병력은 건강에 관한 정보라 가입 때의 포괄 동의로 덮지 않는다.
    const user = userEvent.setup()
    signIn()
    mockApi({})
    renderWithProviders(<OnboardingPage />)

    // 아무것도 안 골랐을 때는 묻지 않는다 - 수집하지 않는 것에 동의를 요구하면
    // 동의가 형식이 된다.
    await screen.findByRole('button', { name: '달걀' })
    expect(screen.queryByLabelText(/알레르기·병력 정보 수집에 동의/)).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '달걀' }))
    expect(screen.getByLabelText(/알레르기·병력 정보 수집에 동의/)).toBeInTheDocument()
  })

  it('동의하지 않으면 건강 정보를 보내지 않는다', async () => {
    const user = userEvent.setup()
    signIn()
    const fetchMock = mockApi({})
    renderWithProviders(<OnboardingPage />)

    await user.click(await screen.findByRole('button', { name: '달걀' }))
    await fillRequired(user)
    await user.click(screen.getByRole('button', { name: '저장하기' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('동의')
    expect(
      fetchMock.mock.calls.some(([, init]) => (init as RequestInit | undefined)?.method === 'PUT'),
    ).toBe(false)
  })

  it('동의하면 동의 여부를 함께 보낸다', async () => {
    const user = userEvent.setup()
    signIn()
    const fetchMock = mockApi({})
    renderWithProviders(<OnboardingPage />)

    await user.click(await screen.findByRole('button', { name: '달걀' }))
    await user.click(screen.getByLabelText(/알레르기·병력 정보 수집에 동의/))
    await fillRequired(user)
    await user.click(screen.getByRole('button', { name: '저장하기' }))

    await waitFor(() => {
      const body = putBody(fetchMock)
      expect(body.health_data_consent).toBe(true)
      expect(body.allergy).toBe('달걀')
    })
  })

  it('이미 동의했으면 체크된 상태로 보여준다', async () => {
    // 동의한 사람에게 빈 체크박스를 보여주면 "동의한 적 없다"는 인상을 준다.
    signIn()
    mockApi({
      profile: profile({ has_profile: true, allergy: '우유', health_data_consent: true }),
    })
    renderWithProviders(<OnboardingPage />)

    await waitFor(() =>
      expect(screen.getByLabelText(/알레르기·병력 정보 수집에 동의/)).toBeChecked(),
    )
  })

  it('알레르기 목록을 못 받으면 알린다', async () => {
    // 목록이 비면 화면상으로는 "알레르기 없음"과 구분되지 않는다. 조용히 넘기면
    // 사용자는 고를 게 없는 줄 알고 그냥 저장한다.
    signIn()
    mockApi({ allergyStatus: 500, allergyOptions: { detail: '서버 오류' } })
    renderWithProviders(<OnboardingPage />)

    expect(await screen.findByRole('alert')).toHaveTextContent('알레르기 목록')
  })

  it('프로필을 못 읽었으면 폼을 내주지 않는다', async () => {
    // 성별·연령대를 모르는 채로 PUT을 보내면 가입 때 받은 값이 빈 문자열로 덮인다.
    signIn()
    mockApi({ profileStatus: 500, profile: { detail: '서버 오류' } })
    renderWithProviders(<OnboardingPage />)

    await screen.findByRole('alert')
    expect(screen.queryByRole('button', { name: '저장하기' })).not.toBeInTheDocument()
  })

  it('프로필이 오기 전에는 폼을 내주지 않는다', async () => {
    // 폼을 먼저 내주면 사용자가 고른 칩이 프로필 도착 시 초기값으로 덮여 사라진다.
    // 브라우저 확인 중에 실제로 그랬다 - 알레르기를 골랐는데 조용히 비워졌다.
    signIn()
    let releaseProfile: () => void = () => {}
    const pending = new Promise<void>((resolve) => {
      releaseProfile = resolve
    })
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      if (String(input).includes('/profile/options')) return json(PROFILE_OPTIONS)
      if (String(input).includes('/profile/allergy-options')) return json(ALLERGY_OPTIONS)
      await pending
      return json(profile())
    })
    renderWithProviders(<OnboardingPage />)

    expect(await screen.findByRole('status')).toHaveTextContent('불러오는 중')
    expect(screen.queryByRole('button', { name: '달걀' })).not.toBeInTheDocument()

    releaseProfile()
    expect(await screen.findByRole('button', { name: '달걀' })).toBeInTheDocument()
  })

  it('저장이 실패하면 알리고 화면에 머문다', async () => {
    const user = userEvent.setup()
    signIn()
    mockApi({ putStatus: 500 })
    renderWithProviders(<OnboardingPage />)

    await screen.findByRole('button', { name: '달걀' })
    await fillRequired(user)
    await user.click(screen.getByRole('button', { name: '저장하기' }))

    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '저장하기' })).toBeEnabled()
  })
})
