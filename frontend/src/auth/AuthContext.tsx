import { useCallback, useMemo, useState, type ReactNode } from 'react'

import * as authApi from '../api/auth'
import { AuthContext, type AuthState } from './context'

export function AuthProvider({ children }: { children: ReactNode }) {
  // 새로고침해도 유지되도록 저장소에서 시작 상태를 읽는다.
  const [userId, setUserId] = useState<number | null>(() => authApi.sessionStore.getUserId())

  const login = useCallback(async (username: string, password: string) => {
    setUserId(await authApi.login(username, password))
  }, [])

  const signup = useCallback(async (body: authApi.SignupBody) => {
    setUserId(await authApi.signup(body))
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
