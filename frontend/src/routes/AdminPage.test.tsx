import { act, screen, waitFor } from '@testing-library/react'
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

const pendingIngredient = {
  id: 13,
  ingredient_name: '자색당근',
  calorie: 41,
  username: '채소사랑',
}

function deferredResponse() {
  let resolve!: (response: Response) => void
  const promise = new Promise<Response>((complete) => { resolve = complete })
  return { promise, resolve }
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

    await user.click(await screen.findByRole('button', { name: '자장면 승인' }))

    await waitFor(() => expect(screen.queryByText('자장면')).toBeNull())
    const approvedCall = fetchMock.mock.calls.find(([url]) =>
      String(url).includes('/admin/recipes/1198/approve'),
    )
    expect(approvedCall).toBeDefined()
    expect(screen.getByRole('status')).toHaveTextContent('자장면 승인을 완료했어요.')
    expect(screen.getByRole('heading', { name: '승인 대기 목록' })).toHaveFocus()
  })

  it('거절은 확인을 받고 나서만 보낸다', async () => {
    // 거절은 레시피를 지운다. 되돌릴 수 없어서 한 번 묻는다.
    const user = userEvent.setup()
    signIn()
    const fetchMock = mockApi({ recipes: [pendingRecipe] })
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false)
    renderWithProviders(<AdminPage />)

    await user.click(await screen.findByRole('button', { name: '자장면 거절' }))

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

  it('목록 조회 실패를 대기 0건으로 표시하지 않고 재시도할 수 있다', async () => {
    signIn()
    const user = userEvent.setup()
    let failed = true
    const retryRecipes = deferredResponse()
    const retryIngredients = deferredResponse()
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      if (failed) return json({ detail: '목록 연결 실패' }, 500)
      return new URL(String(input)).pathname.endsWith('/pending-recipes')
        ? retryRecipes.promise
        : retryIngredients.promise
    })
    renderWithProviders(<AdminPage />)

    expect(await screen.findByRole('alert')).toHaveTextContent('승인 대기 목록을 불러오지 못했어요.')
    expect(screen.queryByText(/승인을 기다리는/)).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: '레시피 0건' })).not.toBeInTheDocument()
    failed = false
    await user.click(screen.getByRole('button', { name: '대기 목록 다시 불러오기' }))

    expect(screen.getByRole('status')).toHaveTextContent('승인 대기 목록을 불러오는 중…')
    expect(screen.queryByText(/승인을 기다리는/)).not.toBeInTheDocument()
    await act(async () => {
      retryRecipes.resolve(json([pendingRecipe]))
      retryIngredients.resolve(json([pendingIngredient]))
    })
    expect(await screen.findByRole('button', { name: '자장면 승인' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '자색당근 거절' })).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('레시피 1건, 재료 1건')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '승인 대기 목록' })).toHaveFocus()
  })

  it('같은 순간의 연속 승인과 처리 중 다른 결정을 막는다', async () => {
    signIn()
    const response = deferredResponse()
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      if (init?.method === 'POST') return response.promise
      return json(new URL(String(input)).pathname.endsWith('/pending-recipes') ? [pendingRecipe] : [])
    })
    renderWithProviders(<AdminPage />)
    const approve = await screen.findByRole('button', { name: '자장면 승인' })
    approve.focus()

    act(() => {
      approve.click()
      approve.click()
    })

    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(1)
    expect(approve).toBeDisabled()
    expect(screen.getByRole('button', { name: '자장면 거절' })).toBeDisabled()
    expect(approve.closest('li')).toHaveAttribute('aria-busy', 'true')
    expect(screen.getByRole('status')).toHaveTextContent('자장면 승인 처리 중…')
    await act(async () => { response.resolve(json({ approved: true })) })
    await waitFor(() => expect(approve).toBeEnabled())
  })

  it('승인 요청이 실패하면 목록을 유지하고 다시 처리할 수 있다', async () => {
    signIn()
    const user = userEvent.setup()
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      if (init?.method === 'POST') return json({ detail: '승인 실패' }, 500)
      return json(new URL(String(input)).pathname.endsWith('/pending-recipes') ? [pendingRecipe] : [])
    })
    renderWithProviders(<AdminPage />)
    await user.click(await screen.findByRole('button', { name: '자장면 승인' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('승인 실패')
    expect(screen.getByRole('button', { name: '자장면 승인' })).toBeEnabled()
    expect(screen.getByRole('button', { name: '자장면 승인' })).toHaveFocus()
    expect(screen.getByRole('link', { name: '자장면' })).toBeInTheDocument()
    expect(screen.getByRole('status')).not.toHaveTextContent('완료했어요')
  })

  it('승인 성공 뒤 목록 갱신 실패는 처리 실패나 빈 목록으로 바꾸지 않는다', async () => {
    signIn()
    const user = userEvent.setup()
    let approved = false
    let failRefresh = true
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      if (init?.method === 'POST') {
        approved = true
        return json({ approved: true })
      }
      if (approved && failRefresh) return json({ detail: '갱신 실패' }, 500)
      return json(!approved && new URL(String(input)).pathname.endsWith('/pending-recipes') ? [pendingRecipe] : [])
    })
    renderWithProviders(<AdminPage />)
    await user.click(await screen.findByRole('button', { name: '자장면 승인' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('갱신 실패')
    expect(screen.getByRole('status')).toHaveTextContent('자장면 승인을 완료했어요.')
    expect(screen.queryByText(/승인을 기다리는/)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '자장면 승인' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '대기 목록 다시 불러오기' })).toHaveFocus()
    failRefresh = false
    await user.click(screen.getByRole('button', { name: '대기 목록 다시 불러오기' }))
    expect(await screen.findByText('승인을 기다리는 레시피가 없어요.')).toBeInTheDocument()
  })

  it('처리한 항목이 사라지면 다음 대기 항목의 승인 버튼으로 초점을 잇는다', async () => {
    signIn()
    const user = userEvent.setup()
    let approved = false
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      if (init?.method === 'POST') {
        approved = true
        return json({ approved: true })
      }
      return json(new URL(String(input)).pathname.endsWith('/pending-recipes')
        ? approved ? [] : [pendingRecipe]
        : [pendingIngredient])
    })
    renderWithProviders(<AdminPage />)
    await user.click(await screen.findByRole('button', { name: '자장면 승인' }))

    await waitFor(() => expect(screen.queryByRole('link', { name: '자장면' })).not.toBeInTheDocument())
    expect(screen.getByRole('button', { name: '자색당근 승인' })).toHaveFocus()
  })

  it('처리를 기다리며 다른 곳으로 이동하면 완료 후 초점을 빼앗지 않는다', async () => {
    signIn()
    const user = userEvent.setup()
    const response = deferredResponse()
    let approved = false
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      if (init?.method === 'POST') {
        await response.promise
        approved = true
        return json({ approved: true })
      }
      return json(!approved && new URL(String(input)).pathname.endsWith('/pending-recipes') ? [pendingRecipe] : [])
    })
    renderWithProviders(<><a href="#other">다른 작업으로</a><AdminPage /></>)
    await user.click(await screen.findByRole('button', { name: '자장면 승인' }))
    screen.getByRole('link', { name: '다른 작업으로' }).focus()
    await act(async () => { response.resolve(json({ approved: true })) })

    await waitFor(() => expect(screen.queryByRole('link', { name: '자장면' })).not.toBeInTheDocument())
    expect(screen.getByRole('link', { name: '다른 작업으로' })).toHaveFocus()
  })

  it('재료 거절도 항목 이름을 안내하고 기존 API로 한 번만 처리한다', async () => {
    signIn()
    const user = userEvent.setup()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    let rejected = false
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      if (init?.method === 'POST') {
        rejected = true
        return json({ approved: false })
      }
      return json(!rejected && new URL(String(input)).pathname.endsWith('/pending-ingredients') ? [pendingIngredient] : [])
    })
    renderWithProviders(<AdminPage />)
    await user.click(await screen.findByRole('button', { name: '자색당근 거절' }))

    await waitFor(() => expect(screen.queryByRole('button', { name: '자색당근 거절' })).not.toBeInTheDocument())
    expect(screen.getByRole('status')).toHaveTextContent('자색당근 거절을 완료했어요.')
    expect(fetchMock.mock.calls.filter(([url, init]) => init?.method === 'POST' && String(url).includes('/admin/ingredients/13/reject'))).toHaveLength(1)
    expect(screen.getByRole('heading', { name: '승인 대기 목록' })).toHaveFocus()
  })
})
