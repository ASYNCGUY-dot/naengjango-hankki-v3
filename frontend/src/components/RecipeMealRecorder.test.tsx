import { act, fireEvent, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { createMeal } from '../api/meals'
import { renderWithProviders } from '../test/renderWithProviders'
import RecipeMealRecorder from './RecipeMealRecorder'

vi.mock('../api/meals', () => ({ createMeal: vi.fn() }))

const meal = { id: 1, recipe_id: 67, recipe_name: '두부덮밥', servings: 1, consumed_at: '2026-10-24T03:00:00Z' }

describe('레시피에서 먹었어요', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.mocked(createMeal).mockReset().mockResolvedValue(meal)
  })
  afterEach(() => vi.restoreAllMocks())

  function signIn() {
    localStorage.setItem('naengjango.userId', '116')
    localStorage.setItem('naengjango.token', 'test-token')
  }

  it('로그인 전에는 기록을 보내지 않고 로그인으로 안내한다', async () => {
    renderWithProviders(<RecipeMealRecorder recipeId={67} />)
    expect(screen.getByRole('link', { name: /로그인하고 식사 기록/ })).toHaveAttribute('href', '/login')
    expect(createMeal).not.toHaveBeenCalled()
  })

  it('먹은 양을 선택하고 눌러야 기록하며 마이로 이어준다', async () => {
    signIn()
    const user = userEvent.setup()
    renderWithProviders(<RecipeMealRecorder recipeId={67} />)
    expect(createMeal).not.toHaveBeenCalled()
    await user.selectOptions(screen.getByLabelText('먹은 양'), '0.5')
    await user.click(screen.getByRole('button', { name: '먹었어요' }))
    expect(createMeal).toHaveBeenCalledWith({ recipe_id: 67, servings: 0.5, request_id: expect.any(String) })
    expect(await screen.findByRole('status')).toHaveTextContent('기록했어요')
    expect(screen.getByRole('link', { name: '마이에서 확인' })).toHaveAttribute('href', '/my')
  })

  it('응답을 기다리는 동안 연타해도 요청은 하나다', async () => {
    signIn()
    let resolve!: (value: typeof meal) => void
    vi.mocked(createMeal).mockReturnValue(new Promise(r => { resolve = r }))
    renderWithProviders(<RecipeMealRecorder recipeId={67} />)
    const button = screen.getByRole('button', { name: '먹었어요' })
    fireEvent.click(button)
    fireEvent.click(button)
    expect(createMeal).toHaveBeenCalledTimes(1)
    expect(screen.getByLabelText('먹은 양')).toBeDisabled()
    await act(async () => { resolve(meal) })
  })

  it('통신 실패 후에는 같은 요청 ID로 재시도해 중복 저장을 막는다', async () => {
    signIn()
    const user = userEvent.setup()
    vi.mocked(createMeal).mockRejectedValueOnce(new TypeError('offline'))
    renderWithProviders(<RecipeMealRecorder recipeId={67} />)
    await user.click(screen.getByRole('button', { name: '먹었어요' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('다시')
    const first = vi.mocked(createMeal).mock.calls[0][0]
    await user.click(screen.getByRole('button', { name: '다시 기록 확인' }))
    expect(vi.mocked(createMeal).mock.calls[1][0]).toEqual(first)
    expect(await screen.findByRole('status')).toHaveTextContent('기록했어요')
  })

  it('같은 메뉴를 다시 먹었을 때만 새 요청으로 한 끼를 추가한다', async () => {
    signIn()
    const user = userEvent.setup()
    renderWithProviders(<RecipeMealRecorder recipeId={67} />)
    await user.click(screen.getByRole('button', { name: '먹었어요' }))
    await user.click(await screen.findByRole('button', { name: '한 번 더 기록하기' }))
    expect(createMeal).toHaveBeenCalledTimes(1)
    await user.click(screen.getByRole('button', { name: '먹었어요' }))
    expect(createMeal).toHaveBeenCalledTimes(2)
    expect(vi.mocked(createMeal).mock.calls[1][0].request_id).not.toBe(vi.mocked(createMeal).mock.calls[0][0].request_id)
  })

  it('다른 레시피로 이동하면 이전 레시피의 늦은 저장 응답을 표시하지 않는다', async () => {
    signIn()
    let resolve!: (value: typeof meal) => void
    vi.mocked(createMeal).mockReturnValue(new Promise(r => { resolve = r }))
    function RecipeSwitcher() {
      const [recipeId, setRecipeId] = useState(67)
      return <><button onClick={() => setRecipeId(68)}>다른 레시피</button><RecipeMealRecorder recipeId={recipeId} /></>
    }
    renderWithProviders(<RecipeSwitcher />)
    fireEvent.click(screen.getByRole('button', { name: '먹었어요' }))
    fireEvent.click(screen.getByRole('button', { name: '다른 레시피' }))
    await act(async () => { resolve(meal) })
    expect(screen.queryByText(/기록했어요/)).not.toBeInTheDocument()
  })
})
