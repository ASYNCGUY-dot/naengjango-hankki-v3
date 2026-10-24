import { useEffect, useId, useRef, useState } from 'react'
import { Link } from 'react-router-dom'

import { ApiError } from '../api/client'
import { createMeal, type MealEntry } from '../api/meals'
import { useAuth } from '../auth/context'
import styles from './RecipeMealRecorder.module.css'

export default function RecipeMealRecorder({ recipeId }: { recipeId: number }) {
  const { userId, isAuthenticated } = useAuth()
  if (!isAuthenticated || userId === null) return (
    <section className={styles.card} aria-label="식사 기록">
      <p>먹은 메뉴를 기록하면 마이에서 오늘의 영양을 확인할 수 있어요.</p>
      <Link to="/login">로그인하고 식사 기록하기</Link>
    </section>
  )
  return <Recorder key={`${userId}:${recipeId}`} recipeId={recipeId} />
}

function Recorder({ recipeId }: { recipeId: number }) {
  const amountId = useId()
  const [servings, setServings] = useState(1)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [uncertain, setUncertain] = useState(false)
  const [saved, setSaved] = useState<MealEntry | null>(null)
  const pending = useRef(false)
  const live = useRef(true)
  const attempt = useRef<{ recipe_id: number; servings: number; request_id: string } | null>(null)

  useEffect(() => {
    live.current = true
    return () => { live.current = false }
  }, [])

  async function record() {
    if (pending.current || saved !== null) return
    pending.current = true
    setBusy(true)
    setError(null)
    try {
      // 응답이 끊겨도 같은 식사로 재전송한다. 저장 확인 전에는 ID와 양을 유지한다.
      attempt.current ??= { recipe_id: recipeId, servings, request_id: crypto.randomUUID() }
      const meal = await createMeal(attempt.current)
      if (!live.current) return
      setSaved(meal)
      setUncertain(false)
      attempt.current = null
    } catch (caught) {
      if (!live.current) return
      if (caught instanceof ApiError && caught.status < 500) {
        setError(caught.message)
        setUncertain(false)
        attempt.current = null
      } else {
        setError('저장 여부를 확인하지 못했어요. 다시 눌러 확인해주세요.')
        setUncertain(true)
      }
    } finally {
      if (live.current) {
        pending.current = false
        setBusy(false)
      }
    }
  }

  return (
    <section className={styles.card} aria-label="식사 기록">
      <div className={styles.heading}>
        <h2>이 메뉴 드셨나요?</h2>
        <p>먹은 만큼 오늘의 영양에 더해요.</p>
      </div>
      {saved === null ? <form className={styles.form} onSubmit={event => { event.preventDefault(); void record() }}>
        <label htmlFor={amountId}>먹은 양</label>
        <select id={amountId} value={servings} disabled={busy || uncertain} onChange={event => setServings(Number(event.target.value))}>
          {[0.5, 1, 1.5, 2].map(amount => <option key={amount} value={amount}>{amount}인분</option>)}
        </select>
        <button className={styles.primary} type="submit" disabled={busy}>
          {busy ? '기록 중…' : uncertain ? '다시 기록 확인' : '먹었어요'}
        </button>
      </form> : <>
        <p className={styles.success} role="status">{saved.servings}인분 식사를 기록했어요.</p>
        <div className={styles.actions}>
          <Link to="/my">마이에서 확인</Link>
          <button className={styles.secondary} type="button" onClick={() => { setSaved(null); setError(null) }}>한 번 더 기록하기</button>
        </div>
      </>}
      {error && <p className={styles.error} role="alert">{error} <Link to="/my">마이에서 확인</Link></p>}
      <p className={styles.hint}>마이에서 양을 수정하거나 기록을 취소할 수 있어요.</p>
    </section>
  )
}
