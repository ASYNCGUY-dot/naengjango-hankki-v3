import { useEffect, useState } from 'react'

import { listFavorites, toggleFavorite } from '../api/favorites'
import { useAuth } from '../auth/context'
import styles from './FavoriteButton.module.css'

/**
 * 즐겨찾기 - 내가 다시 보려고 나에게 담아두는 별.
 *
 * 옆의 추천하기(RecommendButton)와 다른 기능이다. 즐겨찾기는 나만 보고, 추천은 남에게
 * 보인다. 서버에서도 테이블이 갈라져 있다(favorites vs recipe_likes). 그래서 아이콘도
 * 별과 하트로 나누고 글자도 다르게 쓴다 - 둘 다 하트면 사용자는 자기가 무엇을 눌렀는지
 * 알 수 없다.
 *
 * 서버에는 원래부터 있던 기능인데 화면이 부르지 않아 아무도 못 썼다(2026-08-18까지).
 * 마음에 든 레시피를 다시 찾으려면 이름을 기억해서 검색하는 수밖에 없었다. 재방문율이
 * Phase 4의 핵심 지표인데 다시 올 이유 하나가 닫혀 있던 셈이다.
 *
 * 지금 상태를 알아내려고 목록 전체를 받아 확인한다. 한 사람의 즐겨찾기는 작아서
 * 그걸로 충분하고, "이 레시피가 담겨 있나"만 묻는 엔드포인트를 새로 만들 이유가 없다.
 *
 * 누르면 화면을 먼저 바꾸고 서버에 보낸다. 무료 서버에서 왕복이 2초 넘게 걸릴 수 있는데
 * 그동안 별이 그대로면 안 눌린 줄 알고 또 누른다 - 그러면 껐다 켜져서 담긴 것이 풀린다.
 * 실패하면 되돌리고 이유를 알린다.
 */
export default function FavoriteButton({ recipeId }: { recipeId: number }) {
  const { userId, isAuthenticated } = useAuth()
  const [isFavorited, setIsFavorited] = useState(false)
  const [isReady, setIsReady] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (userId === null) return
    const controller = new AbortController()
    listFavorites(userId, controller.signal)
      .then((items) => {
        setIsFavorited(items.some((item) => item.id === recipeId))
        setIsReady(true)
      })
      // 목록을 못 받으면 지금 상태를 모른다. 하트를 안 보여주는 편이 낫다 -
      // 빈 하트를 보여주면 "저장 안 됨"이라는 틀린 정보를 준다.
      .catch(() => {})
    return () => controller.abort()
  }, [recipeId, userId])

  if (!isAuthenticated || !isReady) return null

  async function handleToggle() {
    if (userId === null) return
    const next = !isFavorited
    setIsFavorited(next)
    setError(null)
    try {
      const saved = await toggleFavorite(userId, recipeId)
      // 서버가 말하는 상태를 최종으로 삼는다. 다른 기기에서 이미 바꿨을 수 있다.
      setIsFavorited(saved)
    } catch {
      setIsFavorited(!next)
      setError('즐겨찾기에 담지 못했어요. 잠시 후 다시 시도해주세요.')
    }
  }

  return (
    <>
      <button
        className={isFavorited ? `${styles.button} ${styles.on}` : styles.button}
        type="button"
        aria-pressed={isFavorited}
        onClick={() => void handleToggle()}
      >
        <span aria-hidden="true">{isFavorited ? '★' : '☆'}</span>
        {isFavorited ? '즐겨찾기됨' : '즐겨찾기'}
      </button>
      {error !== null && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}
    </>
  )
}
