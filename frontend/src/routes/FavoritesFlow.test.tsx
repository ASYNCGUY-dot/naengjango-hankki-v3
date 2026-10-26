import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from '../App'
import type { FavoriteItem } from '../api/favorites'
import { renderWithProviders } from '../test/renderWithProviders'
import { dailyNutrition } from '../test/mealFixtures'

const saved: FavoriteItem[] = Array.from({ length: 5 }, (_, i) => ({
  id: 67 + i,
  menu_name: ['블랙빈 곤약국수', '닭고기김치찌개', '애호박들깨볶음', '일본식 계란말이', '옥수수감자샐러드'][i],
  category: i === 0 ? null : '반찬',
  calorie: i === 0 ? null : 100 + i,
  image_url: i === 0 ? null : `https://example.com/recipe-${i}.jpg`,
  created_at: '2026-10-22T00:00:00Z',
}))

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

function api(items = saved, options: { failLoad?: boolean; failRemove?: boolean; pendingToggle?: Promise<void> } = {}) {
  let rows = [...items]
  let toggleCount = 0
  let failLoad = options.failLoad ?? false
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = new URL(String(input))
    if (url.pathname === '/meals/today') return json(dailyNutrition())
    if (url.pathname.startsWith('/favorites/')) {
      if (init?.method === 'POST') {
        toggleCount += 1
        if (options.pendingToggle) await options.pendingToggle
        if (options.failRemove) return json({ detail: '잠시 후 다시 시도해주세요.' }, 500)
        const id = Number(url.pathname.split('/')[3])
        const existing = rows.some(item => item.id === id)
        rows = existing ? rows.filter(item => item.id !== id) : [saved.find(item => item.id === id)!, ...rows]
        return json({ favorited: !existing })
      }
      if (failLoad) return json({ detail: '목록 오류' }, 500)
      return json(rows)
    }
    if (url.pathname.startsWith('/profile/')) return json({ name: '테스트', username: 'tester', has_profile: true, is_admin: false })
    return json([])
  })
  return { rows: () => rows, toggleCount: () => toggleCount, recoverLoad: () => { failLoad = false } }
}

describe('즐겨찾기 미리보기와 전체 목록', () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem('naengjango.userId', '116')
    localStorage.setItem('naengjango.token', 'test-token')
    vi.spyOn(window, 'scrollTo').mockImplementation(() => {})
  })
  afterEach(() => vi.restoreAllMocks())

  it('마이에는 3개만 보여주고 전체 개수와 더보기 주소를 표시한다', async () => {
    api()
    renderWithProviders(<App />, { route: '/my' })
    const section = screen.getByRole('region', { name: '즐겨찾기' })
    await within(section).findByRole('link', { name: /블랙빈 곤약국수/ })
    expect(within(section).getAllByRole('listitem')).toHaveLength(3)
    expect(within(section).getByText('5개')).toBeInTheDocument()
    expect(within(section).getByRole('link', { name: '즐겨찾기 더보기' })).toHaveAttribute('href', '/my/favorites')
    expect(within(section).queryByText('일본식 계란말이')).not.toBeInTheDocument()
  })

  it('더보기를 누르면 5개 전체와 마이로 돌아가는 링크가 나온다', async () => {
    api()
    const user = userEvent.setup()
    renderWithProviders(<App />, { route: '/my' })
    await user.click(await screen.findByRole('link', { name: '즐겨찾기 더보기' }))
    expect(screen.getByRole('heading', { level: 1, name: '즐겨찾기' })).toHaveFocus()
    expect(await screen.findAllByRole('listitem')).toHaveLength(5)
    expect(screen.getByRole('link', { name: '마이로 돌아가기' })).toHaveAttribute('href', '/my')
    expect(screen.getByRole('link', { name: '마이' })).toHaveAttribute('aria-current', 'page')
    expect(document.title).toBe('즐겨찾기 | 냉장고 한끼')
  })

  it('3개 이하면 불필요한 더보기를 표시하지 않는다', async () => {
    api(saved.slice(0, 1))
    renderWithProviders(<App />, { route: '/my' })
    expect(await screen.findByText('블랙빈 곤약국수')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: '즐겨찾기 더보기' })).not.toBeInTheDocument()
  })

  it('마이에서 해제하면 다음 저장 메뉴가 미리보기를 채우고 되돌리면 복원된다', async () => {
    const server = api()
    const user = userEvent.setup()
    renderWithProviders(<App />, { route: '/my' })
    await user.click(await screen.findByRole('button', { name: '즐겨찾기 해제: 블랙빈 곤약국수' }))
    await waitFor(() => expect(screen.queryByRole('link', { name: /블랙빈 곤약국수/ })).not.toBeInTheDocument())
    expect(screen.getByText('일본식 계란말이')).toBeInTheDocument()
    expect(screen.getByText('4개')).toBeInTheDocument()
    expect(server.rows()).toHaveLength(4)
    await user.click(screen.getByRole('button', { name: '되돌리기' }))
    expect(await screen.findByRole('link', { name: /블랙빈 곤약국수/ })).toHaveAttribute('href', '/recipe/67')
    expect(screen.getByText('5개')).toBeInTheDocument()
    expect(server.rows()).toHaveLength(5)
  })

  it('전체 화면에서 해제와 되돌리기를 지원한다', async () => {
    api()
    const user = userEvent.setup()
    renderWithProviders(<App />, { route: '/my/favorites' })
    await user.click(await screen.findByRole('button', { name: '즐겨찾기 해제: 옥수수감자샐러드' }))
    await waitFor(() => expect(screen.queryByText('옥수수감자샐러드')).not.toBeInTheDocument())
    expect(screen.getAllByRole('listitem')).toHaveLength(4)
    await user.click(screen.getByRole('button', { name: '되돌리기' }))
    expect(await screen.findAllByRole('listitem')).toHaveLength(5)
  })

  it('해제에 실패하면 메뉴를 유지하고 오류를 알린다', async () => {
    api(saved, { failRemove: true })
    const user = userEvent.setup()
    renderWithProviders(<App />, { route: '/my/favorites' })
    await user.click(await screen.findByRole('button', { name: '즐겨찾기 해제: 블랙빈 곤약국수' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('즐겨찾기를 해제하지 못했어요')
    expect(screen.getAllByRole('listitem')).toHaveLength(5)
    expect(screen.getByRole('button', { name: '즐겨찾기 해제: 블랙빈 곤약국수' })).toBeEnabled()
  })

  it('해제 요청 중 연속 클릭해도 한 번만 변경한다', async () => {
    let finish!: () => void
    const pendingToggle = new Promise<void>(resolve => { finish = resolve })
    const server = api(saved, { pendingToggle })
    renderWithProviders(<App />, { route: '/my/favorites' })
    const button = await screen.findByRole('button', { name: '즐겨찾기 해제: 블랙빈 곤약국수' })
    fireEvent.click(button)
    fireEvent.click(button)
    expect(button).toBeDisabled()
    expect(server.toggleCount()).toBe(1)
    finish()
    await waitFor(() => expect(screen.getAllByRole('listitem')).toHaveLength(4))
  })

  it('전체 목록 실패는 빈 목록과 구분하고 재시도할 수 있다', async () => {
    const server = api(saved, { failLoad: true })
    const user = userEvent.setup()
    renderWithProviders(<App />, { route: '/my/favorites' })
    expect(await screen.findByRole('alert')).toHaveTextContent('즐겨찾기 목록을 불러오지 못했어요')
    server.recoverLoad()
    await user.click(screen.getByRole('button', { name: '즐겨찾기 다시 불러오기' }))
    expect(await screen.findAllByRole('listitem')).toHaveLength(5)
  })

  it('전체 목록이 비면 저장 방법을 안내한다', async () => {
    api([])
    renderWithProviders(<App />, { route: '/my/favorites' })
    expect(await screen.findByText(/여기에 모여요/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /즐겨찾기 해제/ })).not.toBeInTheDocument()
  })
})
