import { apiFetch, tokenStore, type LoginResponse, type SignupResponse } from './client'

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
  const data = await apiFetch<LoginResponse>('/auth/login', {
    method: 'POST',
    body: { username, password },
  })
  sessionStore.save(data.user_id, data.token)
  return data.user_id
}

export async function signup(username: string, password: string): Promise<number> {
  const data = await apiFetch<SignupResponse>('/auth/signup', {
    method: 'POST',
    body: { username, password },
  })
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

/** 백엔드의 MIN_PASSWORD_LENGTH와 같은 값이다(api/routers/auth.py). */
export const MIN_PASSWORD_LENGTH = 8
