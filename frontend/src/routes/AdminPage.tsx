import { useCallback, useEffect, useState } from 'react'
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
import styles from './MyRecipesPage.module.css'

function describe(caught: unknown): string {
  if (caught instanceof ApiError || caught instanceof TimeoutError) return caught.message
  return '요청에 실패했어요. 잠시 후 다시 시도해주세요.'
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

  const [recipes, setRecipes] = useState<PendingRecipe[]>([])
  const [ingredients, setIngredients] = useState<PendingIngredient[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [isForbidden, setIsForbidden] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(
    async (signal?: AbortSignal) => {
      if (userId === null) return
      try {
        const [pendingRecipes, pendingIngredients] = await Promise.all([
          listPendingRecipes(userId, signal),
          listPendingIngredients(userId, signal),
        ])
        setRecipes(pendingRecipes)
        setIngredients(pendingIngredients)
        setIsForbidden(false)
      } catch (caught) {
        if (signal?.aborted) return
        if (caught instanceof ApiError && caught.status === 403) {
          setIsForbidden(true)
        } else {
          setError(describe(caught))
        }
      } finally {
        if (!signal?.aborted) setIsLoading(false)
      }
    },
    [userId],
  )

  useEffect(() => {
    const controller = new AbortController()
    void load(controller.signal)
    return () => controller.abort()
  }, [load])

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

  if (isForbidden) {
    return (
      <div className={styles.guest}>
        <h1>승인 대기 목록</h1>
        <p>관리자 권한이 필요한 화면이에요.</p>
        <Link className={styles.primary} to="/my">
          마이로 돌아가기
        </Link>
      </div>
    )
  }

  async function decide(kind: 'recipe' | 'ingredient', id: number, decision: 'approve' | 'reject') {
    if (userId === null) return
    setError(null)
    try {
      if (kind === 'recipe') {
        await reviewRecipe(id, userId, decision)
      } else {
        await reviewIngredient(id, userId, decision)
      }
      // 목록을 다시 받는다. 눈앞에서만 지우면 서버에서 실패했을 때 처리한 줄 알게 된다.
      await load()
    } catch (caught) {
      setError(describe(caught))
    }
  }

  return (
    <div className={styles.page}>
      <h1>승인 대기 목록</h1>

      {error !== null && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}

      {isLoading ? (
        <p className={styles.empty}>불러오는 중…</p>
      ) : (
        <>
          <h2 className={styles.subhead}>레시피 {recipes.length}건</h2>
          {recipes.length === 0 ? (
            <p className={styles.empty}>승인을 기다리는 레시피가 없어요.</p>
          ) : (
            <ul className={styles.list}>
              {recipes.map((recipe) => (
                <li key={recipe.id}>
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
                  <div className={styles.itemActions}>
                    <button
                      className={styles.ghost}
                      type="button"
                      onClick={() => void decide('recipe', recipe.id, 'approve')}
                    >
                      승인
                    </button>
                    {/* 거절은 레시피를 지운다. 되돌릴 수 없어서 확인을 한 번 받는다. */}
                    <button
                      className={styles.danger}
                      type="button"
                      onClick={() => {
                        if (window.confirm(`"${recipe.menu_name}"을 거절하고 삭제할까요?`)) {
                          void decide('recipe', recipe.id, 'reject')
                        }
                      }}
                    >
                      거절
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}

          <h2 className={styles.subhead}>재료 {ingredients.length}건</h2>
          {ingredients.length === 0 ? (
            <p className={styles.empty}>승인을 기다리는 재료가 없어요.</p>
          ) : (
            <ul className={styles.list}>
              {ingredients.map((item) => (
                <li key={item.id}>
                  <div className={styles.itemHead}>
                    <span className={styles.itemName}>{item.ingredient_name}</span>
                  </div>
                  <p className={styles.itemMeta}>
                    {item.calorie === null ? '열량 미입력' : `${item.calorie} kcal / 100g`} ·{' '}
                    {item.username}
                  </p>
                  <div className={styles.itemActions}>
                    <button
                      className={styles.ghost}
                      type="button"
                      onClick={() => void decide('ingredient', item.id, 'approve')}
                    >
                      승인
                    </button>
                    <button
                      className={styles.danger}
                      type="button"
                      onClick={() => {
                        if (window.confirm(`"${item.ingredient_name}"을 거절하고 삭제할까요?`)) {
                          void decide('ingredient', item.id, 'reject')
                        }
                      }}
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
