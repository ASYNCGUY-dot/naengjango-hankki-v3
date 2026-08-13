import { apiFetch, tokenStore, type LoginResponse, type SignupResponse } from './client'
import type { components } from './schema'

/**
 * 요청 본문에도 생성된 타입을 붙인다.
 *
 * apiFetch의 body는 unknown이라 아무 모양이나 통과한다. 실제로 가입 항목이 늘었을 때
 * 프론트가 옛 본문(아이디·비밀번호만)을 보내고 있었는데 타입 검사가 통과했다. 타입을
 * 넣은 이유가 이런 불일치를 잡는 것이므로, 호출부마다 명세의 요청 타입을 명시한다.
 */
export type SignupBody = components['schemas']['SignupRequest']
export type Consents = components['schemas']['Consents']

/** 새로고침해도 로그인이 유지되도록 user_id도 함께 남긴다(토큰은 tokenStore가 맡는다). */
const USER_ID_KEY = 'naengjango.userId'

export const sessionStore = {
  getUserId(): number | null {
    const raw = localStorage.getItem(USER_ID_KEY)
    if (raw === null) return null
    const parsed = Number(raw)
    return Number.isInteger(parsed) ? parsed : null
  },
  save(userId: number, token: string) {
    localStorage.setItem(USER_ID_KEY, String(userId))
    tokenStore.set(token)
  },
  clear() {
    localStorage.removeItem(USER_ID_KEY)
    tokenStore.clear()
  },
}

export async function login(username: string, password: string): Promise<number> {
  const body: components['schemas']['LoginRequest'] = { username, password }
  const data = await apiFetch<LoginResponse>('/auth/login', { method: 'POST', body })
  sessionStore.save(data.user_id, data.token)
  return data.user_id
}

export async function signup(body: SignupBody): Promise<number> {
  const data = await apiFetch<SignupResponse>('/auth/signup', { method: 'POST', body })
  // 백엔드가 가입 직후 토큰을 함께 준다. 가입하고 다시 로그인하게 만들 이유가 없다.
  sessionStore.save(data.user_id, data.token)
  return data.user_id
}

export async function logout(): Promise<void> {
  try {
    await apiFetch('/auth/logout', { method: 'POST' })
  } finally {
    // 서버 호출이 실패해도 이 기기에서는 로그아웃돼야 한다.
    sessionStore.clear()
  }
}

/**
 * 초기화 링크를 메일로 보내달라고 요청한다.
 *
 * 가입된 주소든 아니든 서버가 같은 응답을 준다 - 어떤 이메일이 가입돼 있는지 알아내는
 * 통로가 되면 안 되기 때문이다. 그래서 화면도 "메일을 보냈다"가 아니라 "가입된 주소라면
 * 메일이 갈 것"이라고 안내해야 한다.
 */
export async function requestPasswordReset(email: string): Promise<void> {
  const body: components['schemas']['PasswordResetRequest'] = { email }
  await apiFetch('/auth/password-reset/request', { method: 'POST', body })
}

export async function confirmPasswordReset(token: string, newPassword: string): Promise<void> {
  const body: components['schemas']['PasswordResetConfirmRequest'] = {
    token,
    new_password: newPassword,
  }
  await apiFetch('/auth/password-reset/confirm', { method: 'POST', body })
}

/** 백엔드의 MIN_PASSWORD_LENGTH와 같은 값이다(api/routers/auth.py). */
export const MIN_PASSWORD_LENGTH = 8

/** 가입 폼의 선택지. 백엔드는 문자열을 그대로 받으므로 화면에서 목록을 정한다. */
export const GENDER_OPTIONS = ['여성', '남성', '선택 안 함'] as const
export const AGE_GROUP_OPTIONS = ['10대', '20대', '30대', '40대', '50대', '60대 이상'] as const
