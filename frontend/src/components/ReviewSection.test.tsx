import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import ReviewSection from './ReviewSection'
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

function review(overrides: Record<string, unknown> = {}) {
  return {
    rating: 5,
    review_text: '간이 딱 맞았어요.',
    created_at: '2026-08-18T09:30:00',
    username: 'jisu',
    image_url: null,
    ...overrides,
  }
}

/** 목록(GET)과 작성(POST)을 method로 갈라 답한다. */
function mockApi(options: { reviews?: unknown[]; postFails?: boolean } = {}) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (_input, init) => {
    if ((init as RequestInit | undefined)?.method === 'POST') {
      if (options.postFails) return json({ detail: '오류' }, 500)
      return json({ saved: true })
    }
    return json(options.reviews ?? [])
  })
}

describe('후기', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.restoreAllMocks())

  it('로그인 없이도 남의 후기는 읽힌다', async () => {
    // 상세는 링크로 공유되는 공개 화면이다. 링크를 받은 사람에게 가장 궁금한 정보다.
    mockApi({ reviews: [review()] })
    renderWithProviders(<ReviewSection recipeId={67} />)

    expect(await screen.findByText('간이 딱 맞았어요.')).toBeInTheDocument()
    expect(screen.getByText(/로그인이 필요해요/)).toBeInTheDocument()
  })

  it('별점을 낭독기가 읽을 수 있게 적는다', async () => {
    // 별 문자만 그리면 소리로는 "★★★★★"가 무슨 뜻인지 알 수 없다.
    mockApi({ reviews: [review({ rating: 4 })] })
    renderWithProviders(<ReviewSection recipeId={67} />)

    expect(await screen.findByLabelText('별점 4점')).toBeInTheDocument()
  })

  it('내용 없이 별점만으로는 남길 수 없다', async () => {
    // 별점만 남기면 다음 사람에게 아무 정보도 안 된다.
    signIn()
    mockApi()
    renderWithProviders(<ReviewSection recipeId={67} />)

    expect(await screen.findByRole('button', { name: '후기 남기기' })).toBeDisabled()
  })

  it('후기를 남기면 목록을 다시 받아 보여준다', async () => {
    const user = userEvent.setup()
    signIn()
    let saved = false
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (_input, init) => {
      if ((init as RequestInit | undefined)?.method === 'POST') {
        saved = true
        return json({ saved: true })
      }
      return json(saved ? [review({ review_text: '방금 남긴 후기' })] : [])
    })
    renderWithProviders(<ReviewSection recipeId={67} />)

    await user.type(await screen.findByLabelText('만들어본 후기'), '방금 남긴 후기')
    await user.click(screen.getByRole('button', { name: '후기 남기기' }))

    expect(await screen.findByText('방금 남긴 후기')).toBeInTheDocument()
    // 입력칸은 비워야 한다. 남아 있으면 같은 후기를 두 번 남기기 쉽다.
    await waitFor(() => expect(screen.getByLabelText('만들어본 후기')).toHaveValue(''))
  })

  it('실패하면 알리고 쓴 내용을 지우지 않는다', async () => {
    // 여기서 내용을 날리면 사용자가 다시 써야 한다.
    const user = userEvent.setup()
    signIn()
    mockApi({ postFails: true })
    renderWithProviders(<ReviewSection recipeId={67} />)

    await user.type(await screen.findByLabelText('만들어본 후기'), '살아남아야 하는 글')
    await user.click(screen.getByRole('button', { name: '후기 남기기' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('후기를 남기지 못했어요')
    expect(screen.getByLabelText('만들어본 후기')).toHaveValue('살아남아야 하는 글')
  })

  it('목록이 배열이 아니어도 화면이 죽지 않는다', async () => {
    // 홈 테마에서 실제로 이렇게 화면 전체가 빈 적이 있다. 후기는 덤이라 그럴 값이 없다.
    vi.spyOn(globalThis, 'fetch').mockImplementation(async () => json({ detail: '이상한 응답' }))
    renderWithProviders(<ReviewSection recipeId={67} />)

    expect(await screen.findByText(/아직 후기가 없어요/)).toBeInTheDocument()
  })
})
