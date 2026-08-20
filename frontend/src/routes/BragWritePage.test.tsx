import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import BragWritePage from './BragWritePage'
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

const RECIPE = {
  id: 67,
  menu_name: '블랙빈 곤약국수',
  cook_method: null,
  category: null,
  calorie: null,
  nutrition_group: null,
  nutrients_json: null,
  steps_json: null,
  youtube_url: null,
  image_url: null,
  ingredients: [],
  base_servings: null,
}

/** 상세·검색·업로드·작성을 경로와 method로 갈라 답한다. */
function mockApi(options: { search?: unknown[]; uploadFails?: boolean } = {}) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const path = new URL(input as string).pathname
    if (path === '/brags/photo') {
      if (options.uploadFails) return json({ detail: '사진을 올리지 못했어요.' }, 502)
      return json({ image_url: 'https://cdn/photo.jpg' })
    }
    if ((init as RequestInit | undefined)?.method === 'POST') return json({ id: 9 })
    if (path.startsWith('/recommendation/recipes/search')) return json(options.search ?? [])
    return json(RECIPE)
  })
}

describe('자랑 글쓰기', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.restoreAllMocks())

  it('레시피 상세에서 오면 그 레시피가 이미 골라져 있다', async () => {
    // 만들고 나서 그 화면을 보고 있을 때 바로 올리는 것이 이 기능의 진짜 흐름이다.
    signIn()
    mockApi()
    renderWithProviders(<BragWritePage />, { route: '/brags/new?recipe=67' })

    expect(await screen.findByText('블랙빈 곤약국수')).toBeInTheDocument()
    // 이미 골랐으면 검색칸을 보여줄 이유가 없다.
    expect(screen.queryByLabelText('레시피 검색')).not.toBeInTheDocument()
  })

  it('탭에서 오면 검색해서 고른다', async () => {
    const user = userEvent.setup()
    signIn()
    mockApi({ search: [{ id: 1, menu_name: '두부조림', category: '반찬', calorie: 120, image_url: null }] })
    renderWithProviders(<BragWritePage />, { route: '/brags/new' })

    await user.type(screen.getByLabelText('레시피 검색'), '두부')

    await user.click(await screen.findByRole('button', { name: '두부조림' }))
    expect(screen.getByText('두부조림')).toBeInTheDocument()
  })

  it('레시피를 고르기 전에는 올릴 수 없다', async () => {
    signIn()
    mockApi()
    renderWithProviders(<BragWritePage />, { route: '/brags/new' })

    expect(screen.getByRole('button', { name: '올리기' })).toBeDisabled()
  })

  it('내용 없이 레시피만으로는 올릴 수 없다', async () => {
    signIn()
    mockApi()
    renderWithProviders(<BragWritePage />, { route: '/brags/new?recipe=67' })

    await screen.findByText('블랙빈 곤약국수')
    expect(screen.getByRole('button', { name: '올리기' })).toBeDisabled()
  })

  it('사진 없이 글만 올릴 수 있다', async () => {
    // 저장소가 없어도 자랑하기 전체가 죽지 않게 만든 것과 짝을 이룬다.
    const user = userEvent.setup()
    signIn()
    const fetchMock = mockApi()
    renderWithProviders(<BragWritePage />, { route: '/brags/new?recipe=67' })

    await screen.findByText('블랙빈 곤약국수')
    await user.type(screen.getByLabelText('어땠나요?'), '사진은 못 찍었어요')
    await user.click(screen.getByRole('button', { name: '올리기' }))

    await waitFor(() => {
      const posted = fetchMock.mock.calls.find(
        ([url, init]) =>
          new URL(url as string).pathname === '/brags' &&
          (init as RequestInit)?.method === 'POST',
      )
      if (posted === undefined) throw new Error('작성 요청이 나가지 않았다')
      const body = JSON.parse((posted[1] as RequestInit).body as string)
      expect(body).toMatchObject({ recipe_id: 67, body: '사진은 못 찍었어요', image_url: null })
    })
    // 사진을 안 골랐으면 업로드는 아예 안 나가야 한다.
    const uploads = fetchMock.mock.calls.filter(
      ([url]) => new URL(url as string).pathname === '/brags/photo',
    )
    expect(uploads).toHaveLength(0)
  })

  it('사진 업로드가 실패하면 이유를 알리고 쓴 글을 지우지 않는다', async () => {
    // 여기서 글을 날리면 사용자가 다시 써야 한다. 업로드와 작성을 나눈 이유가 이것이다.
    const user = userEvent.setup()
    signIn()
    mockApi({ uploadFails: true })
    renderWithProviders(<BragWritePage />, { route: '/brags/new?recipe=67' })

    await screen.findByText('블랙빈 곤약국수')
    await user.type(screen.getByLabelText('어땠나요?'), '살아남아야 하는 글')
    await user.upload(
      screen.getByLabelText('사진 (선택)'),
      new File([new Uint8Array([0xff, 0xd8, 0xff])], 'photo.jpg', { type: 'image/jpeg' }),
    )
    await user.click(screen.getByRole('button', { name: '올리기' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('사진을 올리지 못했어요')
    expect(screen.getByLabelText('어땠나요?')).toHaveValue('살아남아야 하는 글')
  })
})
