import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { ApiError, TimeoutError } from '../api/client'
import { listPantry } from '../api/pantry'
import {
  describeMatch,
  getRecommendations,
  matchLevel,
  type RecommendationItem,
} from '../api/recommend'
import RecipeCard from '../components/RecipeCard'
import { useAuth } from '../auth/context'
import { useSlowRequestHint } from '../hooks/useSlowRequestHint'
import styles from './RecommendPage.module.css'

function describe(caught: unknown): string {
  if (caught instanceof ApiError || caught instanceof TimeoutError) return caught.message
  return '추천을 받아오지 못했어요. 잠시 후 다시 시도해주세요.'
}

/**
 * 추천 결과.
 *
 * 서버가 냉장고를 스스로 읽지 않으므로 화면이 먼저 냉장고를 조회한 뒤 재료 이름을 넘긴다.
 * 그래서 /recommend 주소를 직접 열어도 동작한다 - 냉장고 화면을 거쳐 넘어온 상태에
 * 의존하지 않는다.
 *
 * 이 화면이 부르는 API가 가장 느리다. 콜드스타트에 더해 추천 계산 자체가 서버에서
 * 몇 초 걸린다(Render 무료 티어 0.1 CPU 기준 실측 2.6초, 캐시 적용 후 로컬 0.2초).
 */
export default function RecommendPage() {
  const { userId, isAuthenticated } = useAuth()

  const [items, setItems] = useState<RecommendationItem[]>([])
  const [ingredients, setIngredients] = useState<string[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const isSlow = useSlowRequestHint(isLoading)

  const load = useCallback(
    async (signal?: AbortSignal) => {
      if (userId === null) return
      setIsLoading(true)
      setError(null)
      try {
        const pantry = await listPantry(userId, signal)
        const names = pantry.map((item) => item.name)
        setIngredients(names)

        // 재료가 없으면 추천을 부르지 않는다. 서버가 후보 1,144개를 다 계산하고
        // 아무 재료도 안 맞는 목록을 돌려주는데, 그걸 보여줄 이유가 없다.
        if (names.length === 0) {
          setItems([])
          return
        }
        setItems(await getRecommendations(userId, names, signal))
      } catch (caught) {
        if (signal?.aborted) return
        setError(describe(caught))
        setItems([])
      } finally {
        if (!signal?.aborted) setIsLoading(false)
      }
    },
    [userId],
  )

  useEffect(() => {
    if (userId === null) {
      setIsLoading(false)
      return
    }
    const controller = new AbortController()
    void load(controller.signal)
    return () => controller.abort()
  }, [userId, load])

  if (!isAuthenticated) {
    return (
      <div className={styles.guest}>
        <h1>추천 결과</h1>
        <p>
          냉장고 재료로 추천을 받으려면 로그인이 필요해요.
          <br />
          로그인 없이도 레시피는 둘러볼 수 있어요.
        </p>
        <Link className={styles.cta} to="/login">
          로그인하러 가기
        </Link>
      </div>
    )
  }

  return (
    <>
      <header className={styles.appbar}>
        <h1>추천 결과</h1>
      </header>

      {ingredients.length > 0 && (
        <p className={styles.basis}>
          <span className={styles.basisLabel}>기준 재료</span> {ingredients.join(', ')}
        </p>
      )}

      {isSlow && (
        <p className={styles.notice} role="status">
          <span aria-hidden="true">☕</span>
          <span>
            메뉴를 고르는 중이에요
            <small>재료를 레시피 1,100여 개와 맞춰보고 있어요. 잠시만요.</small>
          </span>
        </p>
      )}

      {error !== null && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}

      {isLoading ? (
        <ul className={styles.grid} aria-hidden="true">
          {Array.from({ length: 4 }, (_, index) => (
            <li key={index} className={styles.skeleton} />
          ))}
        </ul>
      ) : ingredients.length === 0 ? (
        <div className={styles.empty}>
          <p>
            냉장고가 비어 있어요.
            <br />
            재료를 넣으면 그걸로 메뉴를 골라드려요.
          </p>
          <Link className={styles.cta} to="/pantry">
            냉장고 채우러 가기
          </Link>
        </div>
      ) : items.length === 0 && error === null ? (
        <p className={styles.empty}>맞는 메뉴를 찾지 못했어요. 재료를 더 넣어보세요.</p>
      ) : (
        <ul className={styles.grid}>
          {items.map((item) => (
            <li key={item.id}>
              <RecipeCard
                recipe={item}
                badge={{ text: describeMatch(item), tone: matchLevel(item) }}
              />
            </li>
          ))}
        </ul>
      )}

      {!isLoading && items.length > 0 && (
        <p className={styles.footnote}>
          보유 재료를 잘 쓰는 순서예요. 아래로 갈수록 겹치는 재료가 적어요.
        </p>
      )}
    </>
  )
}
