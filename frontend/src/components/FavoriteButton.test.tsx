import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import FavoriteButton from './FavoriteButton'
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

function favorite(id: number) {
  return {
    id,
    menu_name: '테스트',
    category: '반찬',
    calorie: 100,
    image_url: null,
    created_at: '2026-08-18T00:00:00',
  }
}

/** 목록 조회와 토글을 method로 갈라 답한다. */
function mockApi(options: { saved?: number[]; toggleFails?: boolean } = {}) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (_input, init) => {
    if ((init as RequestInit | undefined)?.method === 'POST') {
      if (options.toggleFails) return json({ detail: '오류' }, 500)
      return json({ favorited: true })
    }
    return json((options.saved ?? []).map(favorite))
  })
}

describe('레시피 저장', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.restoreAllMocks())

  it('로그인하지 않으면 아무것도 그리지 않는다', () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
    const { container } = renderWithProviders(<FavoriteButton recipeId={67} />)

    expect(container.querySelector('button')).toBeNull()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('이미 저장한 레시피는 저장된 상태로 보여준다', async () => {
    // 저장해뒀는데 빈 하트가 보이면 "저장 안 됨"이라는 틀린 정보를 준다.
    signIn()
    mockApi({ saved: [67] })
    renderWithProviders(<FavoriteButton recipeId={67} />)

    const button = await screen.findByRole('button', { name: /저장됨/ })
    expect(button).toHaveAttribute('aria-pressed', 'true')
  })

  it('누르면 서버 응답을 기다리지 않고 먼저 바뀐다', async () => {
    // 무료 서버에서 왕복이 2초 넘게 걸릴 수 있다. 그동안 하트가 그대로면 안 눌린 줄
    // 알고 또 누르고, 그러면 껐다 켜져서 저장이 풀린다.
    const user = userEvent.setup()
    signIn()
    let releaseToggle: () => void = () => {}
    const pending = new Promise<void>((resolve) => {
      releaseToggle = resolve
    })
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (_input, init) => {
      if ((init as RequestInit | undefined)?.method === 'POST') {
        await pending
        return json({ favorited: true })
      }
      return json([])
    })
    renderWithProviders(<FavoriteButton recipeId={67} />)

    await user.click(await screen.findByRole('button', { name: /저장하기/ }))
    expect(screen.getByRole('button', { name: /저장됨/ })).toBeInTheDocument()

    releaseToggle()
  })

  it('저장에 실패하면 되돌리고 알린다', async () => {
    // 실패했는데 저장된 것처럼 두면 나중에 마이 화면에서 없는 것을 보고 당황한다.
    const user = userEvent.setup()
    signIn()
    mockApi({ toggleFails: true })
    renderWithProviders(<FavoriteButton recipeId={67} />)

    await user.click(await screen.findByRole('button', { name: /저장하기/ }))

    expect(await screen.findByRole('alert')).toHaveTextContent('저장하지 못했어요')
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /저장하기/ })).toHaveAttribute(
        'aria-pressed',
        'false',
      ),
    )
  })

  it('목록을 못 받으면 하트를 아예 안 보여준다', async () => {
    // 지금 상태를 모르는데 빈 하트를 보여주면 틀린 정보가 된다.
    signIn()
    vi.spyOn(globalThis, 'fetch').mockImplementation(async () => json({ detail: '오류' }, 500))
    const { container } = renderWithProviders(<FavoriteButton recipeId={67} />)

    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(container.querySelector('button')).toBeNull()
  })
})
