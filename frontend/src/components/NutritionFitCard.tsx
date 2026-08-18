import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { getNutritionFit, type NutritionFit } from '../api/recipes'
import { useAuth } from '../auth/context'
import styles from './NutritionFitCard.module.css'

/**
 * "이 레시피가 나에게 어떤 영양소를 채워주나".
 *
 * 온보딩에서 받은 성별·연령대·병력·영양제가 실제로 쓰이는 유일한 자리다. 이 화면이
 * 없던 동안(2026-08-18까지) 그 질문들은 물어만 보고 아무 데도 안 쓰였다.
 *
 * 정확도를 과장하지 않는 것이 이 카드의 핵심이다. 세 가지를 반드시 드러낸다.
 *
 * - `is_estimated` — 성별·연령대가 없어 성인 평균으로 계산했다는 뜻. 개인 기준인 것처럼
 *   보이면 안 된다
 * - `micro_is_partial` — 미량영양소는 영양DB와 이름이 맞는 재료만 더한 부분 합계다.
 *   지금 레시피 재료 2,206종 중 22%만 매칭되므로 **실제보다 적게 나온다.** 이걸 안
 *   밝히면 "이 음식은 칼슘이 6%밖에 없구나"라는 잘못된 결론으로 이어진다
 * - `condition_notes` — 병력에 따른 조정과 주의. 근거가 있는 것만 숫자를 바꾸고
 *   나머지는 문구로만 안내한다(nutrition_target_agent 참고)
 *
 * 나트륨은 다른 행과 의미가 반대다. 채워야 하는 목표가 아니라 넘지 말아야 하는 상한이라
 * 시각적으로도 분리했다.
 */
export default function NutritionFitCard({ recipeId }: { recipeId: number }) {
  const { userId, isAuthenticated } = useAuth()
  const [fit, setFit] = useState<NutritionFit | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    if (userId === null) return
    const controller = new AbortController()
    getNutritionFit(recipeId, userId, controller.signal)
      .then(setFit)
      .catch(() => {
        // 레시피 본문은 이미 보이고 있다. 이 카드 하나 때문에 화면을 망치지 않는다.
        if (!controller.signal.aborted) setFailed(true)
      })
    return () => controller.abort()
  }, [recipeId, userId])

  if (!isAuthenticated) {
    return (
      <section className={styles.card} aria-labelledby="fit-heading">
        <h2 id="fit-heading">나에게 맞는 영양</h2>
        <p className={styles.guide}>
          로그인하고 식단 정보를 입력하면 이 메뉴가 하루 권장량의 얼마를 채워주는지
          알려드려요.
        </p>
      </section>
    )
  }

  if (failed || fit === null) return null

  if (!fit.available) {
    return (
      <section className={styles.card} aria-labelledby="fit-heading">
        <h2 id="fit-heading">나에게 맞는 영양</h2>
        <p className={styles.guide}>
          성별과 연령대를 입력하면 하루 권장량 대비로 알려드려요.{' '}
          <Link to="/onboarding">식단 정보 입력하기</Link>
        </p>
      </section>
    )
  }

  return (
    <section className={styles.card} aria-labelledby="fit-heading">
      <div className={styles.head}>
        <h2 id="fit-heading">나에게 맞는 영양</h2>
        <span className={styles.bracket}>{fit.bracket_label}</span>
      </div>

      {/* 개인 기준이 아닌데 개인 기준처럼 보이면 안 된다. */}
      {fit.is_estimated && (
        <p className={styles.warn}>
          성별·연령대를 몰라 <strong>성인 평균</strong>으로 계산했어요.{' '}
          <Link to="/onboarding">입력하면 더 정확해져요</Link>
        </p>
      )}

      {fit.condition_notes.map((note) => (
        <p className={styles.note} key={note}>
          {note}
        </p>
      ))}

      <ul className={styles.rows}>
        {fit.rows.map((row) => (
          <li key={row.key}>
            <div className={styles.rowHead}>
              <span className={styles.label}>
                {row.label}
                {/* 영양제로 이미 챙기고 있다면 이 음식에서 덜 채워도 된다. */}
                {row.already_supplemented && (
                  <span className={styles.supplement}>영양제로 섭취 중</span>
                )}
              </span>
              {/* 목표값에도 단위를 붙인다. "3.4g / 55"는 55가 무엇인지 알 수 없고,
                  "0.6μg RAE / 650"은 더 읽기 어렵다. */}
              <span className={styles.amount}>
                {row.provided}
                {row.unit}{' '}
                <span className={styles.target}>
                  / {row.target}
                  {row.unit}
                </span>
              </span>
            </div>
            <div className={styles.bar}>
              <div
                className={styles.fill}
                // 100%를 넘어도 막대는 가득까지만. 넘친 양은 아래 숫자가 말해준다.
                style={{ width: `${Math.min(row.pct_of_daily ?? 0, 100)}%` }}
              />
            </div>
            <span className={styles.pct}>하루 권장량의 {row.pct_of_daily ?? 0}%</span>
          </li>
        ))}
      </ul>

      {/* 나트륨은 채우는 목표가 아니라 넘지 않아야 하는 상한이다. 같은 모양으로 그리면
          "1%밖에 안 채웠네"로 잘못 읽힌다. */}
      {fit.sodium_row && (
        <div className={styles.sodium}>
          <div className={styles.rowHead}>
            <span className={styles.label}>
              {fit.sodium_row.label}
              <span className={styles.limitTag}>
                하루 상한 {fit.sodium_row.limit}
                {fit.sodium_row.unit}
                {fit.sodium_row.limit_adjusted && ' (병력 반영)'}
              </span>
            </span>
            <span className={styles.amount}>
              {fit.sodium_row.provided}
              {fit.sodium_row.unit}
            </span>
          </div>
          <span className={styles.pct}>하루 상한의 {fit.sodium_row.pct_of_limit}%를 씁니다</span>
        </div>
      )}

      {/* 안 밝히면 "이 음식은 칼슘이 적구나"라는 잘못된 결론으로 이어진다. */}
      {fit.micro_is_partial && (
        <p className={styles.partial}>
          칼슘·철·아연·비타민은 <strong>영양 정보가 있는 재료만</strong> 더한 값이라 실제보다
          적게 나옵니다. 열량·단백질·나트륨은 레시피에 등록된 값 그대로예요.
        </p>
      )}
    </section>
  )
}
