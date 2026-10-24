import { StrictMode } from 'react'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { Link, MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AuthContext, type AuthState } from '../auth/context'
import FavoritesSection from '../components/FavoritesSection'
import RecipeCard from '../components/RecipeCard'
import { FavoritesProvider } from './FavoritesProvider'
import { useFavorites } from './context'

function json(body: unknown) {
  return new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } })
}

function auth(userId: number | null): AuthState {
  return {
    userId,
    isAuthenticated: userId !== null,
    login: async () => {},
    signup: async () => {},
    logout: async () => {},
  }
}

function Consumer({ load = true }: { load?: boolean }) {
  const state = useFavorites({ load })
  return <>
    <output aria-label="저장한 레시피">{state.isReady ? [...state.favoriteIds].join(',') || '없음' : '대기'}</output>
    <output aria-label="요청 중">{state.busyIds.size}</output>
    <output aria-label="오류">{state.errors.size}</output>
    <button onClick={() => void state.toggle(67)}>67번 토글</button>
  </>
}

function tree(userId: number | null, load = true) {
  return <AuthContext.Provider value={auth(userId)}>
    <FavoritesProvider><Consumer load={load} /></FavoritesProvider>
  </AuthContext.Provider>
}

const savedRecipe = {
  id: 67,
  menu_name: '블랙빈 곤약국수',
  category: '일품',
  calorie: 54,
  image_url: null,
  created_at: '2026-10-24T00:00:00Z',
}

afterEach(() => vi.restoreAllMocks())

describe('목록 카드의 공유 즐겨찾기 상태', () => {
  it('목록 조회가 필요 없는 소비자는 추가 요청을 만들지 않는다', () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
    render(tree(116, false))
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('개발 모드의 효과 재실행에서도 중단한 조회를 다시 시작해 상태를 표시한다', async () => {
    const signals: AbortSignal[] = []
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (_input, init) => {
      signals.push(init!.signal!)
      return json([{ id: 67 }])
    })
    render(<StrictMode>{tree(116)}</StrictMode>)
    await waitFor(() => expect(screen.getByLabelText('저장한 레시피')).toHaveTextContent('67'))
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(signals[0].aborted).toBe(true)
  })

  it('사용자가 바뀌면 이전 목록을 즉시 숨기고 늦은 조회 응답을 무시한다', async () => {
    let release!: (response: Response) => void
    const previous = new Promise<Response>(resolve => { release = resolve })
    let oldSignal: AbortSignal | null = null
    vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
      if (String(input).endsWith('/116')) {
        oldSignal = init!.signal!
        return previous
      }
      return Promise.resolve(json([{ id: 80 }]))
    })
    const view = render(tree(116))
    view.rerender(tree(117))
    expect(oldSignal!.aborted).toBe(true)
    await waitFor(() => expect(screen.getByLabelText('저장한 레시피')).toHaveTextContent('80'))
    await act(async () => { release(json([{ id: 67 }])) })
    expect(screen.getByLabelText('저장한 레시피')).toHaveTextContent('80')
    expect(screen.getByLabelText('저장한 레시피')).not.toHaveTextContent('67')
  })

  it('계정 변경 후 이전 토글의 응답이나 오류가 새 계정에 반영되지 않는다', async () => {
    let fail!: (error: Error) => void
    const pending = new Promise<Response>((_resolve, reject) => { fail = reject })
    vi.spyOn(globalThis, 'fetch').mockImplementation((_input, init) => {
      return init?.method === 'POST' ? pending : Promise.resolve(json([]))
    })
    const view = render(tree(116))
    await waitFor(() => expect(screen.getByLabelText('저장한 레시피')).toHaveTextContent('없음'))
    fireEvent.click(screen.getByRole('button', { name: '67번 토글' }))
    expect(screen.getByLabelText('저장한 레시피')).toHaveTextContent('67')
    expect(screen.getByLabelText('요청 중')).toHaveTextContent('1')
    view.rerender(tree(117))
    await waitFor(() => expect(screen.getByLabelText('저장한 레시피')).toHaveTextContent('없음'))
    await act(async () => { fail(new Error('previous user request failed')) })
    expect(screen.getByLabelText('저장한 레시피')).toHaveTextContent('없음')
    expect(screen.getByLabelText('요청 중')).toHaveTextContent('0')
    expect(screen.getByLabelText('오류')).toHaveTextContent('0')
  })

  it('마이에서 해제 중 목록으로 이동해도 별을 잠그고 중복 토글을 막는다', async () => {
    let release!: (response: Response) => void
    const pending = new Promise<Response>(resolve => { release = resolve })
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((_input, init) => {
      return init?.method === 'POST' ? pending : Promise.resolve(json([savedRecipe]))
    })
    render(<AuthContext.Provider value={auth(116)}>
      <FavoritesProvider><MemoryRouter initialEntries={['/my/favorites']}>
        <Routes>
          <Route path="/my/favorites" element={<><FavoritesSection /><Link to="/">목록으로</Link></>} />
          <Route path="/" element={<><RecipeCard recipe={savedRecipe} /><Consumer /></>} />
        </Routes>
      </MemoryRouter></FavoritesProvider>
    </AuthContext.Provider>)

    fireEvent.click(await screen.findByRole('button', { name: '즐겨찾기 해제: 블랙빈 곤약국수' }))
    fireEvent.click(screen.getByRole('link', { name: '목록으로' }))
    expect(screen.queryByRole('region', { name: '즐겨찾기' })).not.toBeInTheDocument()
    expect(screen.getByLabelText('저장한 레시피')).toHaveTextContent('없음')
    const star = screen.getByRole('button', { name: '즐겨찾기 추가: 블랙빈 곤약국수' })
    expect(star).toBeDisabled()
    fireEvent.click(star)
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(1)
    await act(async () => { release(json({ favorited: false })) })
    expect(star).toBeEnabled()
    expect(screen.getByLabelText('저장한 레시피')).toHaveTextContent('없음')
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method !== 'POST')).toHaveLength(1)
  })

  it('카드에서 해제 중 마이로 이동하면 같은 행을 잠그고 완료 후 목록을 갱신한다', async () => {
    let release!: (response: Response) => void
    const pending = new Promise<Response>(resolve => { release = resolve })
    let favorited = true
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((_input, init) => {
      return init?.method === 'POST' ? pending : Promise.resolve(json(favorited ? [savedRecipe] : []))
    })
    render(<AuthContext.Provider value={auth(116)}>
      <FavoritesProvider><MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route path="/" element={<><RecipeCard recipe={savedRecipe} /><Link to="/my/favorites">마이로</Link></>} />
          <Route path="/my/favorites" element={<FavoritesSection />} />
        </Routes>
      </MemoryRouter></FavoritesProvider>
    </AuthContext.Provider>)

    fireEvent.click(await screen.findByRole('button', { name: '즐겨찾기 해제: 블랙빈 곤약국수' }))
    fireEvent.click(screen.getByRole('link', { name: '마이로' }))
    const remove = await screen.findByRole('button', { name: '즐겨찾기 해제: 블랙빈 곤약국수' })
    expect(remove).toBeDisabled()
    fireEvent.click(remove)
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(1)

    favorited = false
    await act(async () => { release(json({ favorited: false })) })
    await waitFor(() => expect(screen.queryByRole('button', { name: '즐겨찾기 해제: 블랙빈 곤약국수' })).not.toBeInTheDocument())
    expect(screen.getByText(/여기에 모여요/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '되돌리기' })).not.toBeInTheDocument()
  })

  it('마이의 해제와 되돌리기가 공유 즐겨찾기 상태에도 반영된다', async () => {
    let favorited = true
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (_input, init) => {
      if (init?.method !== 'POST') return json([savedRecipe])
      favorited = !favorited
      return json({ favorited })
    })
    render(<AuthContext.Provider value={auth(116)}>
      <FavoritesProvider><MemoryRouter><FavoritesSection /><Consumer load={false} /></MemoryRouter></FavoritesProvider>
    </AuthContext.Provider>)

    fireEvent.click(await screen.findByRole('button', { name: '즐겨찾기 해제: 블랙빈 곤약국수' }))
    await waitFor(() => expect(screen.getByLabelText('저장한 레시피')).toHaveTextContent('없음'))
    fireEvent.click(await screen.findByRole('button', { name: '되돌리기' }))
    await waitFor(() => expect(screen.getByLabelText('저장한 레시피')).toHaveTextContent('67'))
  })
})
