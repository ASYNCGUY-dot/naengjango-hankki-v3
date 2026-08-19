import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import RecommendButton from './RecommendButton'
import { renderWithProviders } from '../test/renderWithProviders'

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function signIn(userId = 116) {
  localStorage.setItem('naengjango.userId', String(userId))
  localStorage.setItem('naengjango.token', 'tok-test')
}

/** 조회(GET)와 토글(POST)을 method로 갈라 답한다. */
function mockApi(options: { liked?: boolean; count?: number; toggleFails?: boolean } = {}) {
  const liked = options.liked ?? false
  const count = options.count ?? 0
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (_input, init) => {
    if ((init as RequestInit | undefined)?.method === 'POST') {
      if (options.toggleFails) return json({ detail: '오류' }, 500)
      return json({ liked: !liked, like_count: liked ? count - 1 : count + 1 })
    }
    return json({ liked, like_count: count })
  })
}

describe('추천하기', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.restoreAllMocks())

  it('로그인하지 않으면 아무것도 그리지 않는다', () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
    const { container } = renderWithProviders(<RecommendButton recipeId={67} />)

    expect(container.querySelector('button')).toBeNull()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('누적 추천 수를 늘 보여준다', async () => {
    // 이 숫자가 버튼의 존재 이유다. 내 행동이 어디에 쓰이는지 안 보이면 누를 이유가 없다.
    signIn()
    mockApi({ count: 12 })
    renderWithProviders(<RecommendButton recipeId={67} />)

    const button = await screen.findByRole('button', { name: /추천하기/ })
    expect(button).toHaveTextContent('12')
  })

  it('이미 추천한 레시피는 추천한 상태로 보여준다', async () => {
    signIn()
    mockApi({ liked: true, count: 3 })
    renderWithProviders(<RecommendButton recipeId={67} />)

    const button = await screen.findByRole('button', { name: /추천함/ })
    expect(button).toHaveAttribute('aria-pressed', 'true')
  })

  it('누르면 서버 응답을 기다리지 않고 숫자까지 먼저 바뀐다', async () => {
    // 무료 서버에서 왕복이 2초 넘게 걸린다. 그동안 그대로면 또 눌러서 추천이 취소된다.
    const user = userEvent.setup()
    signIn()
    let release: () => void = () => {}
    const pending = new Promise<void>((resolve) => {
      release = resolve
    })
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (_input, init) => {
      if ((init as RequestInit | undefined)?.method === 'POST') {
        await pending
        return json({ liked: true, like_count: 6 })
      }
      return json({ liked: false, like_count: 5 })
    })
    renderWithProviders(<RecommendButton recipeId={67} />)

    await user.click(await screen.findByRole('button', { name: /추천하기/ }))
    expect(screen.getByRole('button', { name: /추천함/ })).toHaveTextContent('6')

    release()
  })

  it('실패하면 숫자까지 되돌리고 알린다', async () => {
    // 실패했는데 늘어난 숫자가 남으면, 다음에 열었을 때 줄어든 것처럼 보인다.
    const user = userEvent.setup()
    signIn()
    mockApi({ count: 4, toggleFails: true })
    renderWithProviders(<RecommendButton recipeId={67} />)

    await user.click(await screen.findByRole('button', { name: /추천하기/ }))

    expect(await screen.findByRole('alert')).toHaveTextContent('추천하지 못했어요')
    await waitFor(() => {
      const button = screen.getByRole('button', { name: /추천하기/ })
      expect(button).toHaveAttribute('aria-pressed', 'false')
      expect(button).toHaveTextContent('4')
    })
  })

  it('상태를 못 받으면 버튼을 아예 안 보여준다', async () => {
    // 지금 추천했는지 모르는데 빈 하트를 보여주면 틀린 정보가 된다.
    signIn()
    vi.spyOn(globalThis, 'fetch').mockImplementation(async () => json({ detail: '오류' }, 500))
    const { container } = renderWithProviders(<RecommendButton recipeId={67} />)

    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(container.querySelector('button')).toBeNull()
  })
})
