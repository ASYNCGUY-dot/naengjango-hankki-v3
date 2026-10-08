import { useEffect, useState } from 'react'

import { ApiError } from '../api/client'
import { getRecipePrice, type RecipePrice } from '../api/price'
import { useAuth } from '../auth/context'
import styles from './RecipeCostCard.module.css'

/**
 * "이거 해 먹으면 재료비가 얼마쯤 드나" - KAMIS 농산물 시세로 답한다 (2026-09-30).
 *
 * 서버에는 V2 때부터 이 계산이 있었는데 화면이 한 번도 부르지 않았다. 냉장고 재료로
 * 한 끼를 고르는 앱이라, 부족한 재료를 사야 할 때 "그럼 얼마냐"가 바로 다음 질문이다.
 *
 * 정확도를 과장하지 않는 것이 이 카드의 핵심이다. 셋을 반드시 밝힌다.
 *
 * - **시세를 찾은 재료만 더한 값이다.** 두부·고추장 같은 가공식품은 KAMIS(농·축·수산물)
 *   범위 밖이라 빠진다. 안 밝히면 "이 요리는 2천 원이면 되는구나"로 잘못 읽힌다
 * - **개수 단위를 무게로 바꾼 재료는 추정이다.** 계란 1구=60g처럼 평균 중량으로 환산했다
 * - **어느 날, 어디 시세인지.** 서버가 준 라벨("당일 (09/30)")을 그대로 쓴다
 *
 * 등급 배지(가성비·기본·프리미엄)는 내렸다(2026-10-09). 서버는 아직 `tier`를 보내지만
 * 그리지 않는다. 등급은 재료의 kg당 가격이 같은 부류 중앙값보다 비싼지만 보고 쓰는 양은
 * 보지 않아서, 실제 재료비와 거의 무관했다 - 1인분 재료비 중앙값이 가성비 774원·기본
 * 816원·프리미엄 843원이었고, 47원짜리 배물김치가 프리미엄, 12,719원짜리 떡갈비가
 * 가성비였다. 금액 옆에서 금액과 어긋나는 말을 하는 표시는 없는 편이 낫다.
 */

/** 10원 단위로 반올림한다. 시세 자체가 참고값이라 1원 단위는 거짓 정밀도다. */
function won(amount: number): string {
  if (amount > 0 && amount < 10) return '10원 미만'
  return `${(Math.round(amount / 10) * 10).toLocaleString('ko-KR')}원`
}

type State = 'loading' | 'ready' | 'unavailable' | 'hidden'

export default function RecipeCostCard({ recipeId }: { recipeId: number }) {
  const { userId, isAuthenticated } = useAuth()
  const [price, setPrice] = useState<RecipePrice | null>(null)
  const [state, setState] = useState<State>('loading')

  useEffect(() => {
    if (userId === null) return
    const controller = new AbortController()
    setState('loading')
    getRecipePrice(recipeId, userId, controller.signal)
      .then((result) => {
        setPrice(result)
        setState('ready')
      })
      .catch((caught: unknown) => {
        if (controller.signal.aborted) return
        // 503은 KAMIS가 잠깐 응답하지 않는 것이라 알린다. 그 밖의 실패(재료 수량 정보가
        // 없는 레시피의 404 등)는 카드를 숨긴다 - 레시피 본문은 이미 보이고 있다.
        setState(caught instanceof ApiError && caught.status === 503 ? 'unavailable' : 'hidden')
      })
    return () => controller.abort()
  }, [recipeId, userId])

  const heading = (
    <h2 id="cost-heading">재료비는 얼마나 들까요</h2>
  )

  if (!isAuthenticated) {
    return (
      <section className={styles.card} aria-labelledby="cost-heading">
        {heading}
        <p className={styles.guide}>
          로그인하면 KAMIS 농산물 시세로 이 레시피 재료비를 계산해드려요.
        </p>
      </section>
    )
  }

  if (state === 'hidden') return null

  if (state === 'loading') {
    return (
      <section className={styles.card} aria-labelledby="cost-heading">
        {heading}
        <p className={styles.guide} role="status">
          KAMIS 시세를 불러오는 중이에요…
        </p>
      </section>
    )
  }

  if (state === 'unavailable' || price === null) {
    return (
      <section className={styles.card} aria-labelledby="cost-heading">
        {heading}
        <p className={styles.guide}>KAMIS 시세를 잠시 못 불러왔어요. 잠시 뒤 다시 열어주세요.</p>
      </section>
    )
  }

  // 응답 모양을 그냥 믿지 않는다. 배열이 빠져 있어도 카드가 죽으면 안 된다
  // (홈 화면이 영상 분류 때문에 통째로 빈 화면이 됐던 것과 같은 종류다).
  const included = Array.isArray(price.included) ? price.included : []
  const excluded = Array.isArray(price.excluded) ? price.excluded : []
  const days = Array.isArray(price.basis?.price_days) ? price.basis.price_days : []
  const sorted = [...included].sort((a, b) => b.cost - a.cost)

  return (
    <section className={styles.card} aria-labelledby="cost-heading">
      {heading}

      {included.length === 0 ? (
        <p className={styles.guide}>KAMIS 시세로 계산할 수 있는 재료가 없어요.</p>
      ) : (
        <>
          <p className={styles.total}>
            약 <strong>{won(price.total_cost)}</strong>
          </p>
          <p className={styles.meta}>
            {price.household_size}인분 기준 · 시세를 찾은 재료 {included.length}개
          </p>

          <ul className={styles.list}>
            {sorted.map((item) => (
              <li key={item.ingredient}>
                <span className={styles.name}>
                  {item.ingredient}
                  {/* 개수 단위(계란 10구 등)를 평균 무게로 바꾼 값이다. */}
                  {item.is_estimated && <span className={styles.estimate}>추정</span>}
                </span>
                <span className={styles.amount}>{Math.round(item.amount_g)}g</span>
                <span className={styles.cost}>{won(item.cost)}</span>
              </li>
            ))}
          </ul>

          {/* 안 밝히면 부분 합계가 전체 재료비처럼 읽힌다. */}
          <p className={styles.note}>
            시세를 찾은 재료만 더해서 실제 장보기 비용보다 적게 나와요. 소금·간장 같은 조미료는
            집에 있다고 보고 뺐어요.
          </p>
        </>
      )}

      {excluded.length > 0 && (
        <p className={styles.excluded}>
          빠진 재료 {excluded.length}개: {excluded.map((e) => e.ingredient).join(' · ')}
          <br />
          두부·고추장 같은 가공식품과 양이 안 적힌 재료는 KAMIS 시세로 계산할 수 없어요.
        </p>
      )}

      <p className={styles.source}>
        시세: {price.basis?.provider ?? 'KAMIS'} · {price.basis?.market ?? ''}
        {days[0] && ` · ${days[0]} 기준`}
        {days.length > 1 && ' (일부 재료는 더 이전 시세)'}
      </p>
    </section>
  )
}
