import { act, screen, waitFor } from '@testing-library/react'
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
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (_input, init) => {
      if ((init as RequestInit | undefined)?.method === 'POST') {
        await pending
        return json({ liked: true, like_count: 6 })
      }
      return json({ liked: false, like_count: 5 })
    })
    renderWithProviders(<RecommendButton recipeId={67} />)

    await user.click(await screen.findByRole('button', { name: /추천하기/ }))
    expect(screen.getByRole('button', { name: /추천함/ })).toHaveTextContent('6')
    const pendingButton = screen.getByRole('button', { name: /추천함/ })
    expect(pendingButton).toBeDisabled()
    expect(pendingButton).toHaveAttribute('aria-busy', 'true')
    await user.click(pendingButton)
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(1)

    release()
    await waitFor(() => expect(pendingButton).toBeEnabled())
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

  it('조회 실패를 알리고 재시도하면 실제 추천 상태를 보여준다', async () => {
    signIn()
    const user = userEvent.setup()
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async () => json({ detail: '오류' }, 500))
    renderWithProviders(<RecommendButton recipeId={67} />)
    expect(screen.getByRole('status')).toHaveTextContent('불러오는 중')
    expect(await screen.findByRole('alert')).toHaveTextContent('불러오지 못했어요')
    fetchMock.mockImplementation(async () => json({ liked: true, like_count: 8 }))
    await user.click(screen.getByRole('button', { name: '추천 상태 다시 불러오기' }))
    expect(await screen.findByRole('button', { name: /추천함/ })).toHaveTextContent('8')
  })

  it.each([false, true])('재시도 버튼을 유지하고 다른 입력 중 초점을 옮기지 않는다 (입력 이동: %s)', async (moveFocus) => {
    signIn()
    const user = userEvent.setup()
    let release: (response: Response) => void = () => {}
    const response = new Promise<Response>((resolve) => { release = resolve })
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(json({ detail: '오류' }, 500))
      .mockImplementationOnce(() => response)
    renderWithProviders(<><RecommendButton recipeId={67} /><label>다른 입력<input /></label></>)

    const button = await screen.findByRole('button', { name: '추천 상태 다시 불러오기' })
    await user.click(button)
    expect(button).toBeInTheDocument()
    expect(button).toHaveFocus()
    expect(button).toHaveAttribute('aria-disabled', 'true')
    await user.click(button)
    expect(fetchMock).toHaveBeenCalledTimes(2)
    if (moveFocus) await user.type(screen.getByLabelText('다른 입력'), '작성 중')
    await act(async () => { release(json({ liked: true, like_count: 8 })) })

    expect(await screen.findByRole('button', { name: /추천함/ })).toBe(button)
    expect(button).toHaveTextContent('8')
    expect(moveFocus ? screen.getByLabelText('다른 입력') : button).toHaveFocus()
    if (moveFocus) expect(screen.getByLabelText('다른 입력')).toHaveValue('작성 중')
  })
})
