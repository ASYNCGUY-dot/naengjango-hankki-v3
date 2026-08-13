import { screen, within } from '@testing-library/react'
import { Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import RecipeDetailPage from './RecipeDetailPage'
import {
  groupIngredients,
  parseNutrients,
  parseSteps,
  type RecipeDetail,
} from '../api/recipeDetail'
import { renderWithProviders } from '../test/renderWithProviders'

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

/**
 * 실제 라우트로 감싼다. MemoryRouter에 컴포넌트만 넣으면 ":recipeId" 매칭이 없어
 * useParams가 비고, 화면이 전부 "없는 레시피"로 빠진다.
 */
function renderDetail(route: string) {
  return renderWithProviders(
    <Routes>
      <Route path="/recipe/:recipeId" element={<RecipeDetailPage />} />
    </Routes>,
    { route },
  )
}

/** 운영 DB의 실제 레시피(블랙빈 곤약국수, id=67)를 본떴다. */
function detail(overrides: Partial<RecipeDetail> = {}): RecipeDetail {
  return {
    id: 67,
    menu_name: '블랙빈 곤약국수',
    cook_method: '끓이기',
    category: '일품',
    calorie: 54.3,
    nutrition_group: '단백질',
    nutrients_json: JSON.stringify({
      energy_kcal: '54.3',
      carbs_g: '4.9',
      protein_g: '3.4',
      fat_g: '2.4',
      sodium_mg: '18.5',
    }),
    steps_json: JSON.stringify([
      { step: 1, text: '1. 검은콩을 1시간 찬물에 담가 불린다.', image: 'http://x/1.png' },
      { step: 2, text: '2. 오이는 채 썬다.', image: null },
    ]),
    youtube_url: 'https://youtube.com/watch?v=abc',
    image_url: 'http://www.foodsafetykorea.go.kr/uploadimg/cook/10_00113_2.png',
    base_servings: 2,
    ingredients: [
      { name: '주재료', amount: null, unit: null },
      { name: '실곤약', amount: 440, unit: 'g' },
      { name: '검은콩', amount: 70, unit: 'g' },
      { name: '장식', amount: null, unit: null },
      { name: '오이', amount: 20, unit: 'g' },
    ],
    ...overrides,
  }
}

describe('parseSteps', () => {
  it('원본에 붙어 있는 번호를 떼어낸다', () => {
    // 안 떼면 화면 번호와 겹쳐서 "1. 1. …"이 된다.
    const steps = parseSteps(JSON.stringify([{ text: '1. 콩을 불린다.', image: null }]))
    expect(steps[0].text).toBe('콩을 불린다.')
  })

  it('깨진 JSON이면 빈 목록을 준다', () => {
    expect(parseSteps('{이건 JSON이 아니다')).toEqual([])
    expect(parseSteps(null)).toEqual([])
  })
})

describe('parseNutrients', () => {
  it('문자열로 온 숫자를 숫자로 바꾼다', () => {
    // 원본이 {"energy_kcal": "54.3"}처럼 문자열이라 그대로 쓰면 계산이 어긋난다.
    expect(parseNutrients(JSON.stringify({ energy_kcal: '54.3' })).energy_kcal).toBe(54.3)
  })

  it('값이 없거나 깨졌으면 null이다', () => {
    expect(parseNutrients(null).energy_kcal).toBeNull()
    expect(parseNutrients('깨짐').energy_kcal).toBeNull()
    expect(parseNutrients(JSON.stringify({ energy_kcal: '' })).energy_kcal).toBeNull()
  })
})

describe('groupIngredients', () => {
  it('수량이 없는 행을 구획 제목으로 본다', () => {
    // 원본에 "주재료"·"장식"이 재료처럼 섞여 있다. 그냥 나열하면 재료로 보인다.
    const groups = groupIngredients(detail().ingredients)
    expect(groups.map((g) => g.title)).toEqual(['주재료', '장식'])
    expect(groups[0].items.map((i) => i.name)).toEqual(['실곤약', '검은콩'])
  })

  it('구획 제목이 없으면 하나로 묶는다', () => {
    const groups = groupIngredients([{ name: '두부', amount: 100, unit: 'g' }])
    expect(groups).toHaveLength(1)
    expect(groups[0].title).toBeNull()
  })
})

describe('레시피 상세 화면', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.restoreAllMocks())

  it('로그인 없이도 재료까지 다 보인다', async () => {
    // 링크를 받은 사람은 대개 로그인돼 있지 않다. 재료가 안 보이면 레시피가 아니다.
    vi.spyOn(globalThis, 'fetch').mockImplementation(async () => json(detail()))
    renderDetail('/recipe/67')

    expect(await screen.findByRole('heading', { level: 1, name: '블랙빈 곤약국수' })).toBeInTheDocument()
    expect(screen.getByText('실곤약')).toBeInTheDocument()
    expect(screen.getByText('440 g')).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 3, name: '주재료' })).toBeInTheDocument()
    expect(screen.getByText('2인분 기준')).toBeInTheDocument()
  })

  it('조리 순서에 번호가 겹치지 않는다', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async () => json(detail()))
    renderDetail('/recipe/67')

    expect(await screen.findByText('검은콩을 1시간 찬물에 담가 불린다.')).toBeInTheDocument()
    expect(screen.queryByText(/1\. 검은콩/)).toBeNull()
  })

  it('사진 주소를 https로 바꾼다', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async () => json(detail()))
    const { container } = renderDetail('/recipe/67')

    await screen.findByRole('heading', { level: 1 })
    const images = [...container.querySelectorAll('img')]
    expect(images.length).toBeGreaterThan(0)
    // 본 사진과 단계 사진 모두 원본이 http다.
    expect(images.every((img) => img.getAttribute('src')?.startsWith('https://'))).toBe(true)
  })

  it('영양 정보가 없으면 0이 아니라 -로 표시한다', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async () =>
      json(detail({ nutrients_json: null, calorie: null })),
    )
    renderDetail('/recipe/67')

    await screen.findByRole('heading', { level: 1 })
    const list = screen.getByRole('list', { name: '영양 정보' })
    expect(within(list).getAllByText('-').length).toBeGreaterThan(0)
  })

  it('사진이 없어도 깨지지 않는다', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async () => json(detail({ image_url: null })))
    const { container } = renderDetail('/recipe/67')

    await screen.findByRole('heading', { level: 1 })
    // 본 사진 자리에는 이미지가 없고 단계 사진만 남는다.
    expect(container.querySelectorAll('img')).toHaveLength(1)
  })

  it('없는 레시피면 빈 화면 대신 안내한다', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async () =>
      json({ detail: '존재하지 않는 recipe_id입니다.' }, 404),
    )
    renderDetail('/recipe/999999')

    expect(await screen.findByText(/레시피를 찾을 수 없어요/)).toBeInTheDocument()
  })

  it('주소가 숫자가 아니면 요청하지 않는다', () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
    renderDetail('/recipe/이상한값')

    expect(screen.getByText(/레시피를 찾을 수 없어요/)).toBeInTheDocument()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('유튜브 링크는 새 탭에서 열고 opener를 넘기지 않는다', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async () => json(detail()))
    renderDetail('/recipe/67')

    const link = await screen.findByRole('link', { name: /유튜브/ })
    expect(link).toHaveAttribute('target', '_blank')
    expect(link.getAttribute('rel')).toContain('noopener')
  })

  it('유튜브 링크가 없으면 버튼도 없다', async () => {
    // 1,148개 중 23개가 링크 없이 등록돼 있다.
    vi.spyOn(globalThis, 'fetch').mockImplementation(async () => json(detail({ youtube_url: null })))
    renderDetail('/recipe/67')

    await screen.findByRole('heading', { level: 1 })
    expect(screen.queryByRole('link', { name: /유튜브/ })).toBeNull()
  })
})
