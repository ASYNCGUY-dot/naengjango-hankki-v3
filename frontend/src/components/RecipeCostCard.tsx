import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'

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
 * - **어느 날, 어디 시세인지.** 서버가 준 날짜("10/08")를 그대로 쓴다. "당일"·"1일전" 같은
 *   말은 쓰지 않는다 - 연휴에는 며칠 전 시세라 틀린 말이 된다(서버가 날짜만 준다)
 *
 * 등급 배지(가성비·기본·프리미엄)는 내렸다(2026-10-09). 서버는 아직 `tier`를 보내지만
 * 그리지 않는다. 등급은 재료의 kg당 가격이 같은 부류 중앙값보다 비싼지만 보고 쓰는 양은
 * 보지 않아서, 실제 재료비와 거의 무관했다 - 1인분 재료비 중앙값이 가성비 774원·기본
 * 816원·프리미엄 843원이었고, 47원짜리 배물김치가 프리미엄, 12,719원짜리 떡갈비가
 * 가성비였다. 금액 옆에서 금액과 어긋나는 말을 하는 표시는 없는 편이 낫다.
 */

/** 10원 단위로 반올림한다. 시세 자체가 참고값이라 1원 단위는 거짓 정밀도다. */
function roundToTen(amount: number): number {
  return Math.round(amount / 10) * 10
}

function won(amount: number): string {
  if (amount > 0 && amount < 10) return '10원 미만'
  return `${roundToTen(amount).toLocaleString('ko-KR')}원`
}

/**
 * 못 보여 주는 이유를 넷으로 나눈다(2026-10-18). 전에는 503만 알리고 나머지는 카드를 숨겼다 -
 * 그러면 "이 레시피는 계산이 안 된다", "로그인이 풀렸다", "잠깐 못 받았다"가 전부 카드가 없는
 * 것으로 똑같이 보여서, 다시 해 볼지 로그인할지 그냥 넘어갈지 알 수 없다.
 *
 * - `kamis`: 서버가 KAMIS를 못 받았다(503). 서버가 실패를 캐시하지 않으니 다시 부르면 된다
 * - `network`: 연결 실패·시간 초과·그 밖의 서버 오류. 마찬가지로 다시 부를 수 있다
 * - `auth`: 로그인이 만료됐거나 무효하다(401·403). 다시 불러도 소용없고 로그인해야 한다
 * - `no_quantity`: 재료 양이 안 적힌 레시피(404). 이 레시피는 계산할 수 없다
 */
type Failure = 'kamis' | 'network' | 'auth' | 'no_quantity'

function failureOf(caught: unknown): Failure {
  if (caught instanceof ApiError) {
    if (caught.status === 401 || caught.status === 403) return 'auth'
    // 이 경로의 404는 사실상 재료 수량이 없는 레시피다. 사용자는 토큰 확인에서 이미 걸러지고,
    // 레시피는 상세 화면이 먼저 불러와서 있는 것이 확인된 상태다.
    if (caught.status === 404) return 'no_quantity'
    if (caught.status === 503) return 'kamis'
  }
  return 'network'
}

type State = { kind: 'loading' } | { kind: 'ready'; price: RecipePrice } | { kind: 'failed'; failure: Failure }

export default function RecipeCostCard({ recipeId }: { recipeId: number }) {
  const { userId, isAuthenticated } = useAuth()
  const [state, setState] = useState<State>({ kind: 'loading' })
  // "다시 불러오기"를 누를 때마다 올려서 아래 effect를 다시 돌린다.
  const [attempt, setAttempt] = useState(0)
  const cardRef = useRef<HTMLElement>(null)

  useEffect(() => {
    if (userId === null) return
    const controller = new AbortController()
    setState({ kind: 'loading' })
    getRecipePrice(recipeId, userId, controller.signal)
      .then((price) => setState({ kind: 'ready', price }))
      .catch((caught: unknown) => {
        if (controller.signal.aborted) return
        setState({ kind: 'failed', failure: failureOf(caught) })
      })
    return () => controller.abort()
  }, [recipeId, userId, attempt])

  function retry() {
    // 누른 버튼이 "불러오는 중"으로 바뀌며 사라지면 키보드 초점이 문서 맨 앞으로 튄다.
    // 카드는 상태가 바뀌어도 같은 section이라, 카드에 초점을 두면 그 자리에서 이어서 읽힌다.
    cardRef.current?.focus()
    setAttempt((n) => n + 1)
  }

  const card = (children: ReactNode) => (
    <section ref={cardRef} tabIndex={-1} className={styles.card} aria-labelledby="cost-heading">
      <h2 id="cost-heading">재료비는 얼마나 들까요</h2>
      {children}
    </section>
  )

  if (!isAuthenticated) {
    return card(
      <>
        <p className={styles.guide}>
          로그인하면 KAMIS 농산물 시세로 이 레시피 재료비를 계산해드려요.
        </p>
        <Link className={styles.action} to="/login">
          로그인하기
        </Link>
      </>,
    )
  }

  if (state.kind === 'loading') {
    return card(
      <p className={styles.guide} role="status">
        KAMIS 시세를 불러오는 중이에요…
      </p>,
    )
  }

  if (state.kind === 'failed') {
    const { failure } = state
    if (failure === 'no_quantity') {
      return card(
        <p className={styles.guide}>이 레시피는 재료 양이 적혀 있지 않아 재료비를 계산할 수 없어요.</p>,
      )
    }
    if (failure === 'auth') {
      return card(
        <>
          <p className={styles.guide} role="alert">
            로그인이 만료됐어요. 다시 로그인하면 재료비를 계산해드려요.
          </p>
          <Link className={styles.action} to="/login">
            다시 로그인하기
          </Link>
        </>,
      )
    }
    return card(
      <>
        <p className={styles.guide} role="alert">
          {failure === 'kamis'
            ? 'KAMIS 시세를 잠시 못 불러왔어요.'
            : '재료비를 불러오지 못했어요. 연결이 불안정하거나 서버가 잠시 응답하지 않아요.'}
        </p>
        <button type="button" className={styles.action} onClick={retry}>
          다시 불러오기
        </button>
      </>,
    )
  }

  const { price } = state

  // 응답 모양을 그냥 믿지 않는다. 배열이 빠져 있어도 카드가 죽으면 안 된다
  // (홈 화면이 영상 분류 때문에 통째로 빈 화면이 됐던 것과 같은 종류다).
  const included = Array.isArray(price.included) ? price.included : []
  const excluded = Array.isArray(price.excluded) ? price.excluded : []
  const days = Array.isArray(price.basis?.price_days) ? price.basis.price_days : []
  const sorted = [...included].sort((a, b) => b.cost - a.cost)
  // 합계는 화면에 보이는 줄 금액을 더한 값이다(2026-10-11). 서버의 합계는 반올림 전 값을 더한
  // 것이라, 그것을 따로 반올림하면 줄을 더한 값과 10원씩 어긋난다 - 실제로 줄을 더하면
  // 2,020원인데 합계가 2,030원으로 나와 계산이 틀린 것처럼 보였다. 어차피 "약"으로 쓰는 값이라
  // 몇 원 차이보다 화면 안에서 맞아떨어지는 쪽을 택한다. 줄이 전부 10원 미만이라 더한 값이
  // 0이면 서버 합계로 쓴다("0원"이라고 쓰지 않으려고).
  const shownTotal = included.reduce((sum, item) => sum + roundToTen(item.cost), 0)
  const totalText = won(shownTotal > 0 ? shownTotal : price.total_cost)
  // 부위·품종을 안 적어 같은 품목의 가운데 시세로 계산한 재료(2026-10-17). 확정값처럼 보이면 안 된다.
  const hasRepresentative = included.some((item) => item.match_basis === 'representative')
  // 다른 부위·상태의 시세밖에 없어 뺀 재료. 이유가 안 보이면 계산을 못 한 것처럼 읽힌다.
  const substitutes = excluded.filter(
    (e) => e.reason_code === 'other_cut' || e.reason_code === 'other_state',
  )

  return card(
    <>
      {included.length === 0 ? (
        <p className={styles.guide}>KAMIS 시세로 계산할 수 있는 재료가 없어요.</p>
      ) : (
        <>
          <p className={styles.total}>
            약 <strong>{totalText}</strong>
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
                  {item.match_basis === 'representative' && (
                    <span className={styles.estimate} title="부위나 품종이 안 적혀 있어 같은 품목의 가운데 시세로 계산했어요">
                      대표값
                    </span>
                  )}
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
          {hasRepresentative && (
            <p className={styles.note}>
              대표값: 부위나 품종이 안 적힌 재료는 같은 품목의 가운데 시세로 계산했어요.
            </p>
          )}
        </>
      )}

      {excluded.length > 0 && (
        <p className={styles.excluded}>
          빠진 재료 {excluded.length}개: {excluded.map((e) => e.ingredient).join(' · ')}
          <br />
          두부·고추장 같은 가공식품과 양이 안 적힌 재료는 KAMIS 시세로 계산할 수 없어요.
        </p>
      )}
      {substitutes.length > 0 && (
        <ul className={styles.substitutes}>
          {substitutes.map((e) => (
            <li key={e.ingredient}>
              {e.ingredient}: {e.reason}
            </li>
          ))}
        </ul>
      )}

      <p className={styles.source}>
        시세: {price.basis?.provider ?? 'KAMIS'} · {price.basis?.market ?? ''}
        {days[0] && ` · ${days[0]} 기준`}
        {/* "더 이전"이라고 쓰지 않는다. 가장 많은 날짜를 앞에 쓰는데 나머지가 더 최근일 수도 있다. */}
        {days.length > 1 && ' (일부 재료는 다른 날 시세)'}
      </p>
    </>,
  )
}
