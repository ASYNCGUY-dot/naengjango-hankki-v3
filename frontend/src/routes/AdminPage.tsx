import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'

import {
  listPendingIngredients,
  listPendingRecipes,
  reviewIngredient,
  reviewRecipe,
  type PendingIngredient,
  type PendingRecipe,
} from '../api/admin'
import { ApiError, TimeoutError } from '../api/client'
import { useAuth } from '../auth/context'
import { useDeferredFocus } from '../hooks/비동기초점'
import adminStyles from './관리자목록.module.css'
import styles from './MyRecipesPage.module.css'

function describe(caught: unknown): string {
  if (caught instanceof ApiError || caught instanceof TimeoutError) return caught.message
  return '요청에 실패했어요. 잠시 후 다시 시도해주세요.'
}

type QueueState =
  | { kind: 'loading' }
  | { kind: 'failed'; message: string }
  | { kind: 'forbidden' }
  | { kind: 'ready'; recipes: PendingRecipe[]; ingredients: PendingIngredient[] }

type Decision = 'approve' | 'reject'
type PendingDecision = { key: string; name: string; decision: Decision }
type FocusPlan = {
  canRestore: () => boolean
  trigger: HTMLButtonElement
  candidates: string[]
}

/**
 * 승인 대기 목록 - 관리자만.
 *
 * 이 화면이 없는 동안 등록 기능은 반쪽이었다. 이름이 겹치는 레시피와 공식 DB에 이미 있는
 * 재료는 pending으로 들어가는데, 그걸 처리할 곳이 없으니 영원히 대기 상태로 남았다.
 *
 * 권한은 화면이 판단하지 않는다. 마이 화면에서 링크를 감추는 것은 편의일 뿐이고,
 * 여기 쓰이는 모든 엔드포인트가 서버에서 is_admin을 다시 확인한다. 주소를 직접 치고
 * 들어온 사람에게는 403이 오고, 그때 이 화면은 안내만 보여준다.
 */
export default function AdminPage() {
  const { userId, isAuthenticated } = useAuth()

  const [queue, setQueue] = useState<QueueState>({ kind: 'loading' })
  const [pending, setPending] = useState<PendingDecision | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const pendingRef = useRef(false)
  const headingRef = useRef<HTMLHeadingElement>(null)
  const retryRef = useRef<HTMLButtonElement>(null)
  const approveButtons = useRef(new Map<string, HTMLButtonElement>())
  const focusPlan = useRef<FocusPlan | null>(null)
  const { capture } = useDeferredFocus()

  const load = useCallback(
    async (signal?: AbortSignal, preserveList = false) => {
      if (userId === null) return
      if (!preserveList) setQueue({ kind: 'loading' })
      try {
        const [pendingRecipes, pendingIngredients] = await Promise.all([
          listPendingRecipes(userId, signal),
          listPendingIngredients(userId, signal),
        ])
        if (signal?.aborted) return
        setQueue({ kind: 'ready', recipes: pendingRecipes, ingredients: pendingIngredients })
      } catch (caught) {
        if (signal?.aborted) return
        if (caught instanceof ApiError && caught.status === 403) {
          setQueue({ kind: 'forbidden' })
        } else {
          setQueue({ kind: 'failed', message: describe(caught) })
        }
      }
    },
    [userId],
  )

  useEffect(() => {
    const controller = new AbortController()
    void load(controller.signal)
    return () => controller.abort()
  }, [load])

  useLayoutEffect(() => {
    if (pending !== null || queue.kind === 'loading') return
    const plan = focusPlan.current
    focusPlan.current = null
    if (!plan?.canRestore()) return

    if (queue.kind === 'failed') {
      retryRef.current?.focus()
      return
    }
    if (plan.trigger.isConnected && !plan.trigger.disabled) {
      plan.trigger.focus()
      return
    }
    for (const key of plan.candidates) {
      const button = approveButtons.current.get(key)
      if (button) {
        button.focus()
        return
      }
    }
    headingRef.current?.focus()
  }, [pending, queue])

  if (!isAuthenticated) {
    return (
      <div className={styles.guest}>
        <h1>승인 대기 목록</h1>
        <p>관리자만 볼 수 있는 화면이에요.</p>
        <Link className={styles.primary} to="/login">
          로그인하러 가기
        </Link>
      </div>
    )
  }

  if (queue.kind === 'forbidden') {
    return (
      <div className={styles.guest}>
        <h1 ref={headingRef} tabIndex={-1}>승인 대기 목록</h1>
        <p>관리자 권한이 필요한 화면이에요.</p>
        <Link className={styles.primary} to="/my">
          마이로 돌아가기
        </Link>
      </div>
    )
  }

  async function decide(
    kind: 'recipe' | 'ingredient',
    id: number,
    name: string,
    decision: Decision,
    trigger: HTMLButtonElement,
  ) {
    if (userId === null || pendingRef.current || queue.kind !== 'ready') return
    if (decision === 'reject' && !window.confirm(`"${name}"을 거절하고 삭제할까요?`)) return
    pendingRef.current = true
    const key = `${kind}-${id}`
    const keys = [
      ...queue.recipes.map((recipe) => `recipe-${recipe.id}`),
      ...queue.ingredients.map((item) => `ingredient-${item.id}`),
    ]
    const index = keys.indexOf(key)
    focusPlan.current = {
      canRestore: capture(),
      trigger,
      candidates: [...keys.slice(index + 1), ...keys.slice(0, index).reverse()],
    }
    setPending({ key, name, decision })
    setError(null)
    setNotice(null)
    try {
      if (kind === 'recipe') {
        await reviewRecipe(id, userId, decision)
      } else {
        await reviewIngredient(id, userId, decision)
      }
      // 처리는 성공했지만 목록 갱신은 실패할 수 있으므로 두 결과를 구분한다.
      setNotice(`${name} ${decision === 'approve' ? '승인' : '거절'}을 완료했어요.`)
      await load(undefined, true)
    } catch (caught) {
      setError(describe(caught))
    } finally {
      pendingRef.current = false
      setPending(null)
    }
  }

  function retry(trigger: HTMLButtonElement) {
    focusPlan.current = { canRestore: capture(), trigger, candidates: [] }
    setError(null)
    void load()
  }

  const status = pending !== null
    ? `${pending.name} ${pending.decision === 'approve' ? '승인' : '거절'} 처리 중…`
    : queue.kind === 'loading'
      ? '승인 대기 목록을 불러오는 중…'
      : notice ?? (queue.kind === 'ready'
        ? `대기 목록을 확인했어요. 레시피 ${queue.recipes.length}건, 재료 ${queue.ingredients.length}건이에요.`
        : null)

  return (
    <div className={styles.page}>
      <h1 ref={headingRef} tabIndex={-1}>승인 대기 목록</h1>

      <div role="status">
        {status && <p className={styles.notice}>{status}</p>}
      </div>

      {error !== null && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}

      {queue.kind === 'failed' && (
        <div>
          <p className={styles.error} role="alert">
            승인 대기 목록을 불러오지 못했어요. {queue.message}
          </p>
          <button ref={retryRef} className={styles.ghost} type="button" onClick={(event) => retry(event.currentTarget)}>
            대기 목록 다시 불러오기
          </button>
        </div>
      )}

      {queue.kind === 'ready' && (
        <>
          <h2 className={styles.subhead}>레시피 {queue.recipes.length}건</h2>
          {queue.recipes.length === 0 ? (
            <p className={styles.empty}>승인을 기다리는 레시피가 없어요.</p>
          ) : (
            <ul className={styles.list}>
              {queue.recipes.map((recipe) => (
                <li key={recipe.id} aria-busy={pending?.key === `recipe-${recipe.id}`}>
                  <div className={styles.itemHead}>
                    {/* 승인 전에 내용을 봐야 판단할 수 있다. 상세는 관리자에게도 열려 있다. */}
                    <Link className={styles.itemName} to={`/recipe/${recipe.id}`}>
                      {recipe.menu_name}
                    </Link>
                  </div>
                  <p className={styles.itemMeta}>
                    {recipe.category ?? '미분류'}
                    {recipe.calorie !== null && ` · ${Math.round(recipe.calorie)} kcal`} ·{' '}
                    {recipe.username}
                  </p>
                  <div className={`${styles.itemActions} ${adminStyles.actions}`}>
                    <button
                      ref={(button) => {
                        const key = `recipe-${recipe.id}`
                        if (button) approveButtons.current.set(key, button)
                        else approveButtons.current.delete(key)
                      }}
                      className={styles.ghost}
                      type="button"
                      aria-label={`${recipe.menu_name} 승인`}
                      disabled={pending !== null}
                      onClick={(event) => void decide('recipe', recipe.id, recipe.menu_name, 'approve', event.currentTarget)}
                    >
                      승인
                    </button>
                    {/* 거절은 레시피를 지운다. 되돌릴 수 없어서 확인을 한 번 받는다. */}
                    <button
                      className={styles.danger}
                      type="button"
                      aria-label={`${recipe.menu_name} 거절`}
                      disabled={pending !== null}
                      onClick={(event) => void decide('recipe', recipe.id, recipe.menu_name, 'reject', event.currentTarget)}
                    >
                      거절
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}

          <h2 className={styles.subhead}>재료 {queue.ingredients.length}건</h2>
          {queue.ingredients.length === 0 ? (
            <p className={styles.empty}>승인을 기다리는 재료가 없어요.</p>
          ) : (
            <ul className={styles.list}>
              {queue.ingredients.map((item) => (
                <li key={item.id} aria-busy={pending?.key === `ingredient-${item.id}`}>
                  <div className={styles.itemHead}>
                    <span className={styles.itemName}>{item.ingredient_name}</span>
                  </div>
                  <p className={styles.itemMeta}>
                    {item.calorie === null ? '열량 미입력' : `${item.calorie} kcal / 100g`} ·{' '}
                    {item.username}
                  </p>
                  <div className={`${styles.itemActions} ${adminStyles.actions}`}>
                    <button
                      ref={(button) => {
                        const key = `ingredient-${item.id}`
                        if (button) approveButtons.current.set(key, button)
                        else approveButtons.current.delete(key)
                      }}
                      className={styles.ghost}
                      type="button"
                      aria-label={`${item.ingredient_name} 승인`}
                      disabled={pending !== null}
                      onClick={(event) => void decide('ingredient', item.id, item.ingredient_name, 'approve', event.currentTarget)}
                    >
                      승인
                    </button>
                    <button
                      className={styles.danger}
                      type="button"
                      aria-label={`${item.ingredient_name} 거절`}
                      disabled={pending !== null}
                      onClick={(event) => void decide('ingredient', item.id, item.ingredient_name, 'reject', event.currentTarget)}
                    >
                      거절
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  )
}
