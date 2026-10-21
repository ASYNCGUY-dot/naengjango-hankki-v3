import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import RecipeCostCard from './RecipeCostCard'
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

function body(overrides: Record<string, unknown> = {}) {
  return {
    total_cost: 3244.6,
    included: [
      { ingredient: '양파', matched_name: '양파', matched_kind: '양파', unit: '1kg', unit_price: 2500, match_basis: 'exact', amount_g: 200, cost: 500, is_estimated: false, price_day: '09/30' },
      { ingredient: '달걀', matched_name: '계란', matched_kind: '특란10구', unit: '10구', unit_price: 4000, match_basis: 'exact', amount_g: 120, cost: 800, is_estimated: true, price_day: '09/30' },
      { ingredient: '돼지고기(삼겹살)', matched_name: '돼지', matched_kind: '삼겹살', unit: '1kg', unit_price: 6482, match_basis: 'exact', amount_g: 300, cost: 1944.6, is_estimated: false, price_day: '09/30' },
    ],
    excluded: [
      { ingredient: '두부', reason: 'KAMIS 가격 매칭 안 됨', reason_code: 'no_match' },
      { ingredient: '고추장', reason: 'KAMIS 가격 매칭 안 됨', reason_code: 'no_match' },
    ],
    household_size: 2,
    basis: { provider: 'KAMIS 농산물유통정보(aT)', market: '서울 소매가', price_days: ['09/30'] },
    ...overrides,
  }
}

describe('재료비 카드', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.restoreAllMocks())

  it('로그인하지 않아도 공개 경로로 1인분 재료비를 보여 준다', async () => {
    // 전에는 안내문만 보여서, 레시피 링크를 받은 사람은 KAMIS 재료비를 볼 수 없었다(2026-10-21).
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(body({ household_size: 1 })))
    renderWithProviders(<RecipeCostCard recipeId={67} />)

    expect(await screen.findByText('3,240원')).toBeInTheDocument()
    expect(screen.getByText(/1인분 기준 · 시세를 찾은 재료 3개/)).toBeInTheDocument()
    const url = String(fetchMock.mock.calls[0][0])
    expect(url).toContain('/recommendation/recipes/67/price/public')
    expect(url).not.toContain('user_id')
  })

  it('로그인하지 않았으면 가구원 수 환산은 로그인해야 한다고 알린다', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(body({ household_size: 1 })))
    renderWithProviders(<RecipeCostCard recipeId={67} />)

    expect(await screen.findByText(/로그인하면 가구원 수에 맞춰 계산해드려요/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '로그인하기' })).toHaveAttribute('href', '/login')
    // 상세 화면의 "재료비" 바로가기가 이 id로 카드를 찾는다. 초점을 옮길 수 있어야 한다.
    expect(screen.getByRole('region', { name: '재료비는 얼마나 들까요' })).toHaveAttribute('id', 'recipe-cost')
    expect(screen.getByRole('region', { name: '재료비는 얼마나 들까요' })).toHaveAttribute('tabindex', '-1')
  })

  it('로그인했으면 개인 경로를 부르고 가구원 수 안내는 없다', async () => {
    signIn()
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(body()))
    renderWithProviders(<RecipeCostCard recipeId={67} />)

    await screen.findByText('3,240원')
    const url = String(fetchMock.mock.calls[0][0])
    expect(url).not.toContain('/public')
    expect(url).toContain('user_id=116')
    expect(screen.queryByText(/로그인하면 가구원 수에 맞춰/)).not.toBeInTheDocument()
  })

  it('로그인하지 않았을 때 KAMIS가 응답하지 않아도 다시 불러올 수 있다', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({ detail: 'KAMIS 응답 없음' }, 503))
    renderWithProviders(<RecipeCostCard recipeId={67} />)

    expect(await screen.findByRole('alert')).toHaveTextContent('KAMIS 시세를 잠시 못 불러왔어요.')
    expect(screen.getByRole('button', { name: '다시 불러오기' })).toBeInTheDocument()
  })

  it('재료비를 10원 단위로, 몇 인분 기준인지와 함께 보여준다', async () => {
    signIn()
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(body()))
    renderWithProviders(<RecipeCostCard recipeId={67} />)

    // 3244.6원 -> 3,240원. 1원 단위는 시세가 참고값인데 정밀한 척하는 것이다.
    expect(await screen.findByText('3,240원')).toBeVisible()
    expect(screen.getByText(/2인분 기준 · 시세를 찾은 재료 3개/)).toBeVisible()
    expect(screen.getByText('부분 합계')).toBeVisible()
  })

  it('합계는 화면에 보이는 줄 금액을 더한 값과 같다', async () => {
    // 줄마다 10원 단위로 반올림하는데 합계만 반올림 전 값을 더해 반올림하면 어긋난다.
    // 실제 화면에서 줄을 더하면 2,020원인데 합계가 2,030원으로 나왔다(2026-10-11).
    // 여기서는 404+354+354=1,112원 -> 따로 반올림하면 1,110원, 줄을 더하면 400+350+350=1,100원.
    signIn()
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      json(
        body({
          total_cost: 1112,
          included: [
            { ingredient: '미나리', matched_name: '미나리', amount_g: 20, cost: 404, is_estimated: false, price_day: '10/11' },
            { ingredient: '달걀', matched_name: '계란', amount_g: 50, cost: 354, is_estimated: true, price_day: '10/11' },
            { ingredient: '닭가슴살', matched_name: '닭', amount_g: 60, cost: 354, is_estimated: false, price_day: '10/11' },
          ],
        }),
      ),
    )
    renderWithProviders(<RecipeCostCard recipeId={90} />)

    expect(await screen.findByText('1,100원')).toBeInTheDocument()
    expect(screen.queryByText('1,110원')).not.toBeInTheDocument()
  })

  it('줄이 전부 10원 미만이면 합계를 0원으로 쓰지 않는다', async () => {
    signIn()
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      json(
        body({
          total_cost: 7,
          included: [
            { ingredient: '청양고추', matched_name: '풋고추', amount_g: 1, cost: 4, is_estimated: false, price_day: '10/11' },
            { ingredient: '양파', matched_name: '양파', amount_g: 1, cost: 3, is_estimated: false, price_day: '10/11' },
          ],
        }),
      ),
    )
    renderWithProviders(<RecipeCostCard recipeId={90} />)

    await screen.findByText(/1인분|2인분/)
    expect(screen.queryByText('0원')).not.toBeInTheDocument()
    expect(screen.getByText('10원 미만', { selector: 'strong' })).toBeVisible()
  })

  it('어느 날, 어디 시세인지 서버가 준 그대로 밝힌다', async () => {
    signIn()
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(body()))
    renderWithProviders(<RecipeCostCard recipeId={67} />)

    expect(
      await screen.findByText(/KAMIS 농산물유통정보\(aT\) · 서울 소매가 · 09\/30 기준/),
    ).toBeVisible()
  })

  it('계산 내역을 접어도 부분 합계·추정 안내·출처는 보이고, 펼치면 재료별 내역을 볼 수 있다', async () => {
    // 안 밝히면 "이 요리는 3천 원이면 되는구나"로 읽힌다.
    signIn()
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(body()))
    const user = userEvent.setup()
    renderWithProviders(<RecipeCostCard recipeId={67} />)

    expect(await screen.findByText(/실제 장보기 비용보다 적게 나와요/)).toBeVisible()
    expect(screen.getByText('평균 무게로 환산한 추정값을 포함해요.')).toBeVisible()
    expect(screen.getByText(/KAMIS 농산물유통정보\(aT\) · 서울 소매가 · 09\/30 기준/)).toBeVisible()
    expect(screen.getByText('포함 3개 · 제외 2개')).toBeVisible()
    const summary = screen.getByText(/계산 내역 보기/)
    expect(summary.closest('details')).not.toHaveAttribute('open')
    expect(screen.getByText('돼지고기(삼겹살)')).not.toBeVisible()
    expect(screen.getByText(/빠진 재료 2개: 두부 · 고추장/)).not.toBeVisible()

    await user.click(summary)

    expect(summary.closest('details')).toHaveAttribute('open')
    expect(screen.getByText('돼지고기(삼겹살)')).toBeVisible()
    expect(screen.getByText('1,940원')).toBeVisible()
    expect(screen.getByText(/빠진 재료 2개: 두부 · 고추장/)).toBeVisible()

    await user.click(summary)

    expect(screen.getByText('돼지고기(삼겹살)')).not.toBeVisible()
    expect(screen.getByText('3,240원')).toBeVisible()
    expect(screen.getByText(/실제 장보기 비용보다 적게 나와요/)).toBeVisible()
  })

  it('부위·품종을 안 적은 재료는 대표값이라고 밝힌다', async () => {
    // "쇠고기"처럼 부위가 안 적히면 같은 품목의 가운데 시세로 계산한다. 확정값처럼 보이면 안 된다(2026-10-17).
    signIn()
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      json(
        body({
          included: [
            { ingredient: '쇠고기', matched_name: '소', matched_kind: '양지', unit: '1kg', unit_price: 79000, match_basis: 'representative', amount_g: 100, cost: 7900, is_estimated: false, price_day: '10/15' },
            { ingredient: '양파', matched_name: '양파', matched_kind: '양파', unit: '1kg', unit_price: 2000, match_basis: 'exact', amount_g: 100, cost: 200, is_estimated: false, price_day: '10/15' },
          ],
        }),
      ),
    )
    const user = userEvent.setup()
    renderWithProviders(<RecipeCostCard recipeId={91} />)

    expect(await screen.findByText('8,100원')).toBeInTheDocument()
    expect(screen.getByText('부위·품종의 대표 시세로 계산한 추정값을 포함해요.')).toBeVisible()
    await user.click(screen.getByText(/계산 내역 보기/))
    expect(screen.getAllByText('대표값')).toHaveLength(1)
    expect(screen.getByText(/부위나 품종이 안 적힌 재료는 같은 품목의 가운데 시세/)).toBeVisible()
  })

  it('정확한 시세만 있으면 대표값 표시가 없다', async () => {
    signIn()
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(body()))
    renderWithProviders(<RecipeCostCard recipeId={67} />)

    await screen.findByText('3,240원')
    expect(screen.queryByText('대표값')).not.toBeInTheDocument()
  })

  it('다른 부위·상태 시세라서 뺀 재료는 이유를 보여준다', async () => {
    // 닭가슴살에 닭 전체 시세를 쓰지 않고 뺀다. 왜 빠졌는지 안 보이면 계산을 못 한 것처럼 읽힌다.
    signIn()
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      json(
        body({
          excluded: [
            { ingredient: '닭가슴살', reason: '정확한 부위·품종 시세가 없어요 (KAMIS에는 닭(육계) 시세만 있어요)', reason_code: 'other_cut' },
            { ingredient: '새우', reason: '상태가 다른 품목 시세뿐이에요 (KAMIS에는 건새우 시세만 있어요)', reason_code: 'other_state' },
            { ingredient: '두부', reason: 'KAMIS 가격 매칭 안 됨', reason_code: 'no_match' },
          ],
        }),
      ),
    )
    const user = userEvent.setup()
    renderWithProviders(<RecipeCostCard recipeId={90} />)

    await user.click(await screen.findByText(/계산 내역 보기/))
    expect(screen.getByText(/닭가슴살: 정확한 부위·품종 시세가 없어요 \(KAMIS에는 닭\(육계\) 시세만 있어요\)/)).toBeVisible()
    expect(screen.getByText(/새우: 상태가 다른 품목 시세뿐이에요/)).toBeVisible()
    // 일반 "매칭 안 됨"은 지금처럼 이름만 보인다.
    expect(screen.queryByText(/두부: /)).not.toBeInTheDocument()
    expect(screen.getByText(/빠진 재료 3개/)).toBeInTheDocument()
  })

  it('무게로 환산한 재료에는 추정이라고 붙인다', async () => {
    signIn()
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(body()))
    const user = userEvent.setup()
    renderWithProviders(<RecipeCostCard recipeId={67} />)

    await screen.findByText('3,240원')
    await user.click(screen.getByText(/계산 내역 보기/))
    expect(screen.getAllByText('추정')).toHaveLength(1)
    expect(screen.getByText('추정: 개수 단위로 적힌 재료를 평균 무게로 바꿔 계산했어요.')).toBeVisible()
  })

  it('시세 날짜가 섞여 있으면 일부는 다른 날 값이라고 알린다', async () => {
    // "더 이전"이라고 쓰지 않는다. 가장 많은 날짜를 앞에 쓰는데, 나머지가 더 최근일 수도 있다
    // (연휴에는 대부분 10/08 시세이고 축산물만 10/11이었다).
    signIn()
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      json(body({ basis: { provider: 'KAMIS', market: '서울 소매가', price_days: ['10/08', '10/11'] } })),
    )
    renderWithProviders(<RecipeCostCard recipeId={67} />)

    expect(await screen.findByText(/10\/08 기준 \(일부 재료는 다른 날 시세\)/)).toBeInTheDocument()
    expect(screen.queryByText(/더 이전/)).not.toBeInTheDocument()
  })

  it.each(['가성비', '기본', '프리미엄', '정보부족'])(
    '예전 서버처럼 등급(%s)이 와도 배지와 설명을 그리지 않고 금액만 보여준다',
    async (tier) => {
      // 등급은 실제 재료비와 거의 무관했다(2026-10-07 측정: 1인분 재료비 중앙값이 가성비
      // 774원·기본 816원·프리미엄 843원, 47원짜리 배물김치가 프리미엄). 금액 옆에 붙으면
      // 금액과 어긋나는 말을 하게 되므로 내렸다. 서버도 2026-10-20부터 보내지 않는다.
      signIn()
      vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(body({ tier })))
      renderWithProviders(<RecipeCostCard recipeId={67} />)

      await screen.findByText('3,240원')
      expect(screen.queryByText(tier)).not.toBeInTheDocument()
      expect(screen.queryByText(/같은 부류 시세/)).not.toBeInTheDocument()
    },
  )

  it('계산할 재료가 하나도 없으면 금액 대신 그렇다고 말한다', async () => {
    signIn()
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(body({ included: [], total_cost: 0 })))
    renderWithProviders(<RecipeCostCard recipeId={67} />)

    expect(await screen.findByText('KAMIS 시세로 계산할 수 있는 재료가 없어요.')).toBeInTheDocument()
    expect(screen.queryByText(/0원/)).not.toBeInTheDocument()
  })

  it('KAMIS가 응답하지 않으면(503) 알리고, 다시 불러오면 재료비를 보여준다', async () => {
    signIn()
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(json({ detail: 'KAMIS 응답 없음' }, 503))
      .mockResolvedValueOnce(json(body()))
    const user = userEvent.setup()
    renderWithProviders(<RecipeCostCard recipeId={67} />)

    expect(await screen.findByRole('alert')).toHaveTextContent('KAMIS 시세를 잠시 못 불러왔어요.')
    await user.click(screen.getByRole('button', { name: '다시 불러오기' }))

    expect(await screen.findByText('3,240원')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('연결이 끊겨도 카드를 숨기지 않고 다시 불러올 수 있게 한다', async () => {
    // 전에는 503이 아닌 실패는 전부 카드를 숨겨서, 잠깐 끊긴 것과 계산이 안 되는 레시피가 똑같이 보였다.
    signIn()
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('Failed to fetch'))
    renderWithProviders(<RecipeCostCard recipeId={67} />)

    expect(await screen.findByRole('alert')).toHaveTextContent('재료비를 불러오지 못했어요.')
    expect(screen.getByRole('button', { name: '다시 불러오기' })).toBeInTheDocument()
  })

  it('서버 오류(500)도 다시 불러올 수 있다', async () => {
    signIn()
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({ detail: 'Internal Server Error' }, 500))
    renderWithProviders(<RecipeCostCard recipeId={67} />)

    expect(await screen.findByRole('alert')).toHaveTextContent('재료비를 불러오지 못했어요.')
    expect(screen.getByRole('button', { name: '다시 불러오기' })).toBeInTheDocument()
  })

  it('다시 불러오기를 눌러도 키보드 초점이 카드에 남는다', async () => {
    signIn()
    vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(json({ detail: 'KAMIS 응답 없음' }, 503))
      .mockResolvedValueOnce(json({ detail: 'KAMIS 응답 없음' }, 503))
    const user = userEvent.setup()
    renderWithProviders(<RecipeCostCard recipeId={67} />)

    await user.click(await screen.findByRole('button', { name: '다시 불러오기' }))

    // 버튼이 "불러오는 중"으로 바뀌며 사라져도 초점이 문서 맨 앞(body)으로 튀지 않는다.
    expect(document.activeElement).toBe(screen.getByRole('region', { name: '재료비는 얼마나 들까요' }))
    expect(await screen.findByRole('button', { name: '다시 불러오기' })).toBeInTheDocument()
  })

  it('로그인이 만료되면(401) 다시 불러오기 대신 다시 로그인하라고 한다', async () => {
    signIn()
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({ detail: '로그인이 만료되었습니다.' }, 401))
    renderWithProviders(<RecipeCostCard recipeId={67} />)

    expect(await screen.findByRole('alert')).toHaveTextContent('로그인이 만료됐어요.')
    expect(screen.getByRole('link', { name: '다시 로그인하기' })).toHaveAttribute('href', '/login')
    expect(screen.queryByRole('button', { name: '다시 불러오기' })).not.toBeInTheDocument()
  })

  it('재료 수량 정보가 없는 레시피(404)는 계산할 수 없다고 말한다', async () => {
    // 다시 불러와도 결과가 같으니 버튼을 주지 않는다.
    signIn()
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({ detail: '수량 정보 없음' }, 404))
    renderWithProviders(<RecipeCostCard recipeId={67} />)

    expect(await screen.findByText(/재료 양이 적혀 있지 않아 재료비를 계산할 수 없어요/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '다시 불러오기' })).not.toBeInTheDocument()
  })

  it('이번 조회가 실패해 이전 시세로 계산했으면 그렇다고 밝힌다', async () => {
    signIn()
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      json(body({ basis: { provider: 'KAMIS 농산물유통정보(aT)', market: '서울 소매가', price_days: ['09/30'], stale: true, partial: false } })),
    )
    renderWithProviders(<RecipeCostCard recipeId={67} />)

    expect(await screen.findByText(/이전에 받아 둔 시세로 계산했어요/)).toBeVisible()
    expect(screen.queryByText(/시세 일부를 이번에 받지 못해/)).not.toBeInTheDocument()
  })

  it('부류 일부를 못 받았으면 빠진 재료가 더 있을 수 있다고 밝힌다', async () => {
    signIn()
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      json(body({ basis: { provider: 'KAMIS 농산물유통정보(aT)', market: '서울 소매가', price_days: ['09/30'], stale: false, partial: true } })),
    )
    renderWithProviders(<RecipeCostCard recipeId={67} />)

    expect(await screen.findByText(/시세 일부를 이번에 받지 못해/)).toBeVisible()
    expect(screen.queryByText(/이전에 받아 둔 시세로/)).not.toBeInTheDocument()
  })

  it('새로 받은 온전한 시세면 이전 시세·일부 누락 안내가 없다', async () => {
    signIn()
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(body()))
    renderWithProviders(<RecipeCostCard recipeId={67} />)

    expect(await screen.findByText('3,240원')).toBeInTheDocument()
    expect(screen.queryByText(/이전에 받아 둔 시세로/)).not.toBeInTheDocument()
    expect(screen.queryByText(/시세 일부를 이번에 받지 못해/)).not.toBeInTheDocument()
  })

  it('응답 모양이 예상과 달라도 카드가 죽지 않는다', async () => {
    signIn()
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({ tier: '기본', total_cost: 0 }))
    renderWithProviders(<RecipeCostCard recipeId={67} />)

    expect(await screen.findByText('KAMIS 시세로 계산할 수 있는 재료가 없어요.')).toBeInTheDocument()
  })
})
