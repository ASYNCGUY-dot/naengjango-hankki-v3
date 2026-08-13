import { createContext, useContext } from 'react'

import type { SignupBody } from '../api/auth'

/**
 * 컨텍스트와 훅을 컴포넌트 파일에서 분리한다.
 *
 * 한 파일이 컴포넌트와 그 밖의 것을 함께 내보내면 Fast Refresh가 동작하지 않는다.
 * 화면을 고칠 때마다 전체가 새로고침되면 입력해둔 값이 날아가서 개발이 느려진다.
 */
export type AuthState = {
  userId: number | null
  isAuthenticated: boolean
  login: (username: string, password: string) => Promise<void>
  signup: (body: SignupBody) => Promise<void>
  logout: () => Promise<void>
}

export const AuthContext = createContext<AuthState | null>(null)

export function useAuth(): AuthState {
  const value = useContext(AuthContext)
  if (value === null) {
    throw new Error('useAuth는 AuthProvider 안에서만 쓸 수 있습니다.')
  }
  return value
}
