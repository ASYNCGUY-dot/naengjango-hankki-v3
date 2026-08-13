import { render, type RenderResult } from '@testing-library/react'
import type { ReactNode } from 'react'
import { MemoryRouter } from 'react-router-dom'

import { AuthProvider } from '../auth/AuthContext'

/**
 * 실제 앱(main.tsx)과 같은 순서로 감싼다. 테스트가 프로바이더를 빼먹으면 useAuth가
 * 던지는데, 그건 앱의 문제가 아니라 테스트 준비의 문제라 여기서 한 번만 맞춰둔다.
 */
export function renderWithProviders(ui: ReactNode, { route = '/' } = {}): RenderResult {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <AuthProvider>{ui}</AuthProvider>
    </MemoryRouter>,
  )
}
