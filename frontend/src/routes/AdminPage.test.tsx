import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import AdminPage from './AdminPage'
import { renderWithProviders } from '../test/renderWithProviders'

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function signIn(userId = 15) {
  localStorage.setItem('naengjango.userId', String(userId))
  localStorage.setItem('naengjango.token', 'tok-test')
}

/** 두 큐를 경로로 갈라 답하고, 승인·거절은 POST로 받는다. */
function mockApi(options: { recipes?: unknown[]; ingredients?: unknown[]; forbidden?: boolean } = {}) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    if (options.forbidden) return json({ detail: '관리자 권한이 없습니다.' }, 403)
    if ((init as RequestInit | undefined)?.method === 'POST') return json({ approved: true })
    const path = new URL(input as string).pathname
    if (path.endsWith('/pending-recipes')) return json(options.recipes ?? [])
    return json(options.ingredients ?? [])
  })
}

const pendingRecipe = {
  id: 1198,
  menu_name: '자장면',
  category: '일품',
  calorie: 600,
  username: '9256',
}

describe('승인 대기 목록', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.restoreAllMocks())

  it('관리자가 아니면 안내만 보여준다', async () => {
    // 권한 판단은 서버가 한다. 주소를 직접 치고 들어오면 403이 오고 화면이 바뀐다.
    signIn(123)
    mockApi({ forbidden: true })
    renderWithProviders(<AdminPage />)

    expect(await screen.findByText(/관리자 권한이 필요한 화면이에요/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '마이로 돌아가기' })).toHaveAttribute('href', '/my')
  })

  it('대기 중인 레시피를 올린 사람과 함께 보여준다', async () => {
    signIn()
    mockApi({ recipes: [pendingRecipe] })
    renderWithProviders(<AdminPage />)

    expect(await screen.findByRole('link', { name: '자장면' })).toHaveAttribute(
      'href',
      '/recipe/1198',
    )
    expect(screen.getByText(/9256/)).toBeInTheDocument()
  })

  it('승인하면 목록을 서버에서 다시 받는다', async () => {
    // 눈앞에서만 지우면 서버에서 실패했을 때 처리한 줄 알게 된다.
    const user = userEvent.setup()
    signIn()
    let approved = false
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      if ((init as RequestInit | undefined)?.method === 'POST') {
        approved = true
        return json({ approved: true })
      }
      const path = new URL(input as string).pathname
      if (path.endsWith('/pending-recipes')) return json(approved ? [] : [pendingRecipe])
      return json([])
    })
    renderWithProviders(<AdminPage />)

    await user.click(await screen.findByRole('button', { name: '승인' }))

    await waitFor(() => expect(screen.queryByText('자장면')).toBeNull())
    const approvedCall = fetchMock.mock.calls.find(([url]) =>
      String(url).includes('/admin/recipes/1198/approve'),
    )
    expect(approvedCall).toBeDefined()
  })

  it('거절은 확인을 받고 나서만 보낸다', async () => {
    // 거절은 레시피를 지운다. 되돌릴 수 없어서 한 번 묻는다.
    const user = userEvent.setup()
    signIn()
    const fetchMock = mockApi({ recipes: [pendingRecipe] })
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false)
    renderWithProviders(<AdminPage />)

    await user.click(await screen.findByRole('button', { name: '거절' }))

    expect(confirmSpy).toHaveBeenCalled()
    const rejected = fetchMock.mock.calls.filter(([url]) => String(url).includes('/reject'))
    expect(rejected).toHaveLength(0)
  })

  it('둘 다 비면 각각 비었다고 말한다', async () => {
    signIn()
    mockApi()
    renderWithProviders(<AdminPage />)

    expect(await screen.findByText(/승인을 기다리는 레시피가 없어요/)).toBeInTheDocument()
    expect(screen.getByText(/승인을 기다리는 재료가 없어요/)).toBeInTheDocument()
  })
})
