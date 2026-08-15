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
    // 서버 호출이 실패해도 이 기기에서는 반드시 로그아웃돼야 한다.
    // 예외를 그대로 흘리면 setUserId(null)이 실행되지 않아, 토큰은 지워졌는데 화면은
    // 로그인 상태로 남는다. 새로고침 전까지 아무것도 안 되는 상태가 된다.
    try {
      await authApi.logout()
    } finally {
      setUserId(null)
    }
  }, [])

  const value = useMemo<AuthState>(
    () => ({ userId, isAuthenticated: userId !== null, login, signup, logout }),
    [userId, login, signup, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
