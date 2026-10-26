import { useCallback, useEffect, useId, useRef, useState } from 'react'
import { Link } from 'react-router-dom'

import {
  deleteMeal, getMealErrorMessage, getTodayNutrition, MEALS_CHANGED_EVENT, updateMeal,
  type DailyNutrition, type MealEntry,
} from '../api/meals'
import { useAuth } from '../auth/context'
import styles from './DailyNutritionCard.module.css'

type RefreshOptions = { clear?: boolean; discardOnFailure?: boolean }

function MealRow({ meal, busy, onSave, onDelete }: {
  meal: MealEntry
  busy: boolean
  onSave: (meal: MealEntry, servings: number) => void
  onDelete: (meal: MealEntry) => void
}) {
  const [servings, setServings] = useState(meal.servings)
  const selectId = useId()
  useEffect(() => setServings(meal.servings), [meal.servings])
  const quantities = [...new Set([0.5, 1, 1.5, 2, meal.servings])].sort((a, b) => a - b)

  return (
    <li className={styles.meal}>
      <div className={styles.mealTitle}>
        {meal.recipe_id === null ? meal.recipe_name : (
          <Link to={`/recipe/${meal.recipe_id}`}>{meal.recipe_name}</Link>
        )}
        <span>{new Intl.DateTimeFormat('ko-KR', {
          timeZone: 'Asia/Seoul', hour: '2-digit', minute: '2-digit', hour12: false,
        }).format(new Date(meal.consumed_at))}</span>
      </div>
      <div className={styles.mealActions}>
        <label htmlFor={selectId}>먹은 양</label>
        <select id={selectId} value={servings} disabled={busy}
          onChange={(event) => setServings(Number(event.target.value))}>
          {quantities.map((quantity) => (
            <option key={quantity} value={quantity}>{quantity}인분</option>
          ))}
        </select>
        <button type="button" disabled={busy || servings === meal.servings}
          onClick={() => onSave(meal, servings)}>저장</button>
        <button type="button" disabled={busy} onClick={() => onDelete(meal)}>기록 취소</button>
      </div>
    </li>
  )
}

function DailyNutritionContent() {
  const headingId = useId()
  const mealsHeadingId = useId()
  const [daily, setDaily] = useState<DailyNutrition | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [mutationError, setMutationError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [retried, setRetried] = useState(false)
  const mounted = useRef(false)
  const request = useRef<AbortController | null>(null)
  const generation = useRef(0)
  const mutating = useRef(false)
  const changedDuringMutation = useRef(false)
  const deadline = useRef<number | null>(null)
  const resetTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const refreshRef = useRef<(options?: RefreshOptions) => Promise<void>>(async () => {})

  const refresh = useCallback(async (options: RefreshOptions = {}) => {
    if (!mounted.current) return
    request.current?.abort()
    const controller = new AbortController()
    request.current = controller
    const current = ++generation.current
    const startedAt = Date.now()
    const expired = deadline.current !== null && startedAt >= deadline.current
    if (options.clear || expired) {
      setDaily(null)
      setNotice(null)
    }
    setLoading(true)
    setError(null)
    try {
      const result = await getTodayNutrition(controller.signal)
      if (!mounted.current || controller.signal.aborted || current !== generation.current) return
      // 서버가 알려준 자정까지의 간격을 사용하므로 PC의 시간대 설정과 무관하다.
      // 응답이 이동하는 동안 자정이 지난 경우에도 어제의 합계를 다시 표시하지 않는다.
      const remaining = Date.parse(result.next_reset_at) - Date.parse(result.server_now)
      const nextDeadline = startedAt + remaining
      if (!Number.isFinite(remaining) || remaining <= 0) throw new Error('Invalid reset time')
      deadline.current = nextDeadline
      if (resetTimer.current !== null) clearTimeout(resetTimer.current)
      if (nextDeadline <= Date.now()) {
        setDaily(null)
        resetTimer.current = setTimeout(() => {
          void refreshRef.current({ clear: true, discardOnFailure: true })
        }, 1000)
        return
      }
      setDaily(result)
      resetTimer.current = setTimeout(() => {
        // 조회가 실패하더라도 날짜가 지난 합계를 오늘 값으로 남기지 않는다.
        void refreshRef.current({ clear: true, discardOnFailure: true })
      }, Math.min(nextDeadline - Date.now(), 2_147_483_647))
    } catch (caught) {
      if (!mounted.current || controller.signal.aborted || current !== generation.current) return
      if (options.discardOnFailure || (deadline.current !== null && Date.now() >= deadline.current)) {
        setDaily(null)
      }
      setError(getMealErrorMessage(caught, '오늘의 영양을 불러오지 못했어요. 다시 시도해 주세요.'))
    } finally {
      if (mounted.current && !controller.signal.aborted && current === generation.current) {
        setLoading(false)
      }
    }
  }, [])

  useEffect(() => {
    mounted.current = true
    refreshRef.current = refresh
    void refresh()

    const onReturn = () => {
      if (document.visibilityState === 'hidden') return
      void refresh({ discardOnFailure: true })
    }
    const onChanged = () => {
      if (mutating.current) {
        changedDuringMutation.current = true
        return
      }
      void refresh({ discardOnFailure: true })
    }
    window.addEventListener('focus', onReturn)
    document.addEventListener('visibilitychange', onReturn)
    window.addEventListener(MEALS_CHANGED_EVENT, onChanged)
    return () => {
      mounted.current = false
      generation.current += 1
      request.current?.abort()
      if (resetTimer.current !== null) clearTimeout(resetTimer.current)
      window.removeEventListener('focus', onReturn)
      document.removeEventListener('visibilitychange', onReturn)
      window.removeEventListener(MEALS_CHANGED_EVENT, onChanged)
    }
  }, [refresh])

  async function changeMeal(meal: MealEntry, servings?: number) {
    if (mutating.current) return
    mutating.current = true
    changedDuringMutation.current = false
    request.current?.abort()
    generation.current += 1
    setLoading(false)
    setBusy(true)
    setMutationError(null)
    setNotice(null)
    let changed = false
    try {
      if (servings === undefined) await deleteMeal(meal.id)
      else await updateMeal(meal.id, servings)
      changed = true
      if (mounted.current) setNotice(servings === undefined ? '식사 기록을 취소했어요.' : '먹은 양을 수정했어요.')
    } catch {
      if (mounted.current) setMutationError('식사 기록을 변경하지 못했어요. 다시 시도해 주세요.')
    } finally {
      mutating.current = false
      if (mounted.current) {
        setBusy(false)
        if (changed || changedDuringMutation.current) await refresh({ discardOnFailure: true })
      }
    }
  }

  const fit = daily?.nutrition
  const incompleteLabels = daily?.incomplete_nutrients.map((key) => {
    if (key === 'sodium_mg') return fit?.sodium_row?.label ?? '나트륨'
    return fit?.rows.find((row) => row.key === key)?.label ?? ({
      calories: '열량', calories_kcal: '열량', energy_kcal: '열량',
      protein_g: '단백질', calcium_mg: '칼슘', iron_mg: '철', zinc_mg: '아연',
      vitamin_a_ug: '비타민 A', vitamin_c_mg: '비타민 C', vitamin_d_ug: '비타민 D',
    } as Record<string, string>)[key] ?? '일부 영양소'
  }) ?? []

  return (
    <section className={styles.card} aria-labelledby={headingId} aria-busy={loading || busy}>
      <div className={styles.head}>
        <h2 id={headingId}>오늘의 영양</h2>
        {fit?.available && <span className={styles.bracket}>{fit.bracket_label}</span>}
      </div>
      <p className={styles.subtitle}>
        {daily && `${Number(daily.date.slice(5, 7))}월 ${Number(daily.date.slice(8, 10))}일 · `}
        매일 밤 12시, 한국 시간 기준으로 새로 시작해요.
      </p>
      {loading && <p className={styles.guide} role="status">오늘의 영양을 불러오는 중이에요…</p>}
      {error && <p className={styles.error} role="alert">{error}</p>}
      {(error || retried) && <button className={styles.retry} type="button" aria-disabled={loading || busy}
        onClick={() => {
          if (loading || busy) return
          setRetried(true)
          void refresh({ discardOnFailure: true })
        }}>오늘의 영양 다시 불러오기</button>}
      {mutationError && <p className={styles.error} role="alert">{mutationError}</p>}
      {notice && <p className={styles.guide} role="status">{notice}</p>}
      {fit && !fit.available && <p className={styles.guide}>
        성별과 연령대를 입력하면 하루 권장량 대비로 알려드려요.{' '}
        <Link to="/onboarding">식단 정보 입력하기</Link>
      </p>}
      {fit?.available && <>
        {fit.is_estimated && <p className={styles.note}>
          성별·연령대를 몰라 <strong>성인 평균</strong>으로 계산했어요.{' '}
          <Link to="/onboarding">입력하면 더 정확해져요</Link>
        </p>}
        {fit.condition_notes.map((note) => <p key={note} className={styles.note}>{note}</p>)}
        <ul className={styles.rows} aria-label="오늘 섭취한 영양소">
          {fit.rows.map((row) => {
            const percentage = row.pct_of_daily ?? 0
            return <li key={row.key}>
              <div className={styles.rowHead}>
                <span className={styles.label}>{row.label}
                  {row.already_supplemented && <span className={styles.tag}>영양제로 섭취 중</span>}
                </span>
                <span className={styles.amount}>{row.provided}{row.unit}{' '}
                  <span className={styles.target}>/ {row.target}{row.unit}</span>
                </span>
              </div>
              <div className={styles.bar} role="progressbar" aria-label={row.label}
                aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.max(0, Math.min(percentage, 100))}
                aria-valuetext={`${row.provided}${row.unit}, 하루 권장량의 ${percentage}%`}>
                <div className={styles.fill} style={{ width: `${Math.max(0, Math.min(percentage, 100))}%` }} />
              </div>
              <span className={styles.pct}>하루 권장량의 {percentage}%</span>
            </li>
          })}
        </ul>
        {fit.sodium_row && <div className={styles.sodium}>
          <div className={styles.rowHead}>
            <span className={styles.label}>{fit.sodium_row.label}
              <span className={styles.tag}>하루 상한 {fit.sodium_row.limit}{fit.sodium_row.unit}
                {fit.sodium_row.limit_adjusted && ' (병력 반영)'}</span>
            </span>
            <span className={styles.amount}>{fit.sodium_row.provided}{fit.sodium_row.unit}</span>
          </div>
          <p className={styles.pct}>하루 상한의 {fit.sodium_row.pct_of_limit}%를 섭취했어요.</p>
        </div>}
        {fit.micro_is_partial && <p className={styles.guide}>
          칼슘·철·아연·비타민은 <strong>영양 정보가 있는 재료만</strong> 더한 값이라 실제보다 적게 나옵니다.
        </p>}
      </>}
      {incompleteLabels.length > 0 && <p className={styles.note}>
        {Array.from(new Set(incompleteLabels)).join('·')} 정보가 없는 식사가 있어요. 확인되는 값만 합산했어요.
      </p>}
      {daily && <div className={styles.meals}>
        <h3 id={mealsHeadingId}>오늘 먹은 음식 <span>{daily.meals.length}건</span></h3>
        {daily.meals.length === 0 ? <p className={styles.guide}>
          아직 기록한 식사가 없어요. 레시피에서 ‘먹었어요’를 누르면 영양 바가 채워져요.
        </p> : <ul className={styles.mealList} aria-labelledby={mealsHeadingId}>
          {daily.meals.map((meal) => <MealRow key={meal.id} meal={meal} busy={busy || loading}
            onSave={(entry, servings) => void changeMeal(entry, servings)}
            onDelete={(entry) => void changeMeal(entry)} />)}
        </ul>}
        <p className={styles.footnote}>날짜가 바뀌어도 이전 식사 기록은 보관돼요.</p>
      </div>}
    </section>
  )
}

export default function DailyNutritionCard() {
  const { userId, isAuthenticated } = useAuth()
  if (!isAuthenticated || userId === null) return null
  // 계정 전환 시 기존 합계와 진행 중인 요청을 함께 폐기한다.
  return <DailyNutritionContent key={userId} />
}
