import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import PartnerKeyPage from './PartnerKeyPage'
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

describe('재료 구매 수수료 받기', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.restoreAllMocks())

  it('등록 전에는 아직 없다고 말한다', async () => {
    signIn()
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({ registered: false, updated_at: null }))
    renderWithProviders(<PartnerKeyPage />)

    expect(await screen.findByText('아직 등록된 키가 없어요.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '키 등록하기' })).toBeInTheDocument()
  })

  it('쿠팡 승인 전에는 수수료가 안 잡힌다는 것을 미리 알린다', async () => {
    // 이걸 안 적으면 "키를 넣었는데 왜 안 되지"로 남는다. 등록 화면에서만 말할 수 있다.
    signIn()
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({ registered: false, updated_at: null }))
    renderWithProviders(<PartnerKeyPage />)

    expect(await screen.findByText(/누적 판매가 일정 금액을 넘어야/)).toBeInTheDocument()
  })

  it('저장하면 입력칸을 비운다', async () => {
    signIn()
    const user = userEvent.setup()
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (_url, init) => {
      if (init?.method === 'PUT') return json({ registered: true, updated_at: '2026-09-11T00:00:00' })
      return json({ registered: false, updated_at: null })
    })
    renderWithProviders(<PartnerKeyPage />)

    await screen.findByText('아직 등록된 키가 없어요.')
    await user.type(screen.getByLabelText('Access Key'), 'ak-abcdefgh')
    await user.type(screen.getByLabelText('Secret Key'), 'sk-abcdefgh')
    await user.click(screen.getByRole('button', { name: '키 등록하기' }))

    expect(await screen.findByText('저장했어요.')).toBeInTheDocument()
    // 화면에 키를 띄워둘 이유가 없다.
    expect(screen.getByLabelText('Access Key')).toHaveValue('')
    expect(screen.getByLabelText('Secret Key')).toHaveValue('')
  })

  it('시크릿 키는 가려서 입력받는다', async () => {
    signIn()
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({ registered: false, updated_at: null }))
    renderWithProviders(<PartnerKeyPage />)

    await screen.findByText('아직 등록된 키가 없어요.')
    expect(screen.getByLabelText('Secret Key')).toHaveAttribute('type', 'password')
  })

  it('서버가 준 오류 메시지를 그대로 보여준다', async () => {
    signIn()
    const user = userEvent.setup()
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (_url, init) => {
      if (init?.method === 'PUT') return json({ detail: '키를 입력해주세요.' }, 400)
      return json({ registered: false, updated_at: null })
    })
    renderWithProviders(<PartnerKeyPage />)

    await screen.findByText('아직 등록된 키가 없어요.')
    await user.type(screen.getByLabelText('Access Key'), 'ak-abcdefgh')
    await user.type(screen.getByLabelText('Secret Key'), 'sk-abcdefgh')
    await user.click(screen.getByRole('button', { name: '키 등록하기' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('키를 입력해주세요.')
  })

  it('등록돼 있으면 해제 버튼이 보이고, 해제하면 사라진다', async () => {
    signIn()
    const user = userEvent.setup()
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (_url, init) => {
      if (init?.method === 'DELETE') return json({ registered: false, updated_at: null })
      return json({ registered: true, updated_at: '2026-09-11T00:00:00' })
    })
    renderWithProviders(<PartnerKeyPage />)

    await user.click(await screen.findByRole('button', { name: '연동 해제하기' }))

    await waitFor(() =>
      expect(screen.queryByRole('button', { name: '연동 해제하기' })).not.toBeInTheDocument(),
    )
    expect(screen.getByText('아직 등록된 키가 없어요.')).toBeInTheDocument()
  })

  it('상태 조회가 실패해도 화면이 죽지 않는다', async () => {
    // 무료 티어에서 첫 요청이 깨지는 일이 있다. 그때 빈 화면이 되면 안 된다.
    signIn()
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('network'))
    renderWithProviders(<PartnerKeyPage />)

    expect(await screen.findByText('아직 등록된 키가 없어요.')).toBeInTheDocument()
  })
})

describe('기준 숫자는 서버가 정한다', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.restoreAllMocks())

  it('서버가 내려준 기준을 그대로 보여준다', async () => {
    signIn()
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      json({ registered: false, updated_at: null, revenue_min_likes: 100 }),
    )
    renderWithProviders(<PartnerKeyPage />)

    expect(await screen.findByText(/추천 100회/)).toBeInTheDocument()
  })

  it('기준이 바뀌면 화면도 따라 바뀐다', async () => {
    // 화면이 숫자를 따로 들고 있으면 여기서 100이 그대로 나온다.
    signIn()
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      json({ registered: false, updated_at: null, revenue_min_likes: 42 }),
    )
    renderWithProviders(<PartnerKeyPage />)

    expect(await screen.findByText(/추천 42회/)).toBeInTheDocument()
  })

  it('기준을 못 받으면 숫자를 지어내지 않는다', async () => {
    signIn()
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('network'))
    renderWithProviders(<PartnerKeyPage />)

    expect(await screen.findByText(/추천 여러회/)).toBeInTheDocument()
    expect(screen.queryByText(/추천 0회/)).not.toBeInTheDocument()
  })
})
