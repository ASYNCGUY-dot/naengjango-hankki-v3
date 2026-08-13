import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'

import * as authApi from '../api/auth'

type AuthState = {
  userId: number | null
  isAuthenticated: boolean
  login: (username: string, password: string) => Promise<void>
  signup: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  // 새로고침해도 유지되도록 저장소에서 시작 상태를 읽는다.
  const [userId, setUserId] = useState<number | null>(() => authApi.sessionStore.getUserId())

  const login = useCallback(async (username: string, password: string) => {
    setUserId(await authApi.login(username, password))
  }, [])

  const signup = useCallback(async (username: string, password: string) => {
    setUserId(await authApi.signup(username, password))
  }, [])

  const logout = useCallback(async () => {
    await authApi.logout()
    setUserId(null)
  }, [])

  const value = useMemo<AuthState>(
    () => ({ userId, isAuthenticated: userId !== null, login, signup, logout }),
    [userId, login, signup, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthState {
  const value = useContext(AuthContext)
  if (value === null) {
    throw new Error('useAuth는 AuthProvider 안에서만 쓸 수 있습니다.')
  }
  return value
}
