import { useEffect, useRef, useState } from 'react'

import { getLikeStatus, toggleLike } from '../api/likes'
import { useAuth } from '../auth/context'
import styles from './RecommendButton.module.css'

/**
 * 추천하기 - 남에게 보이는 공개 지표.
 *
 * 목록 사진의 즐겨찾기(FavoriteButton)와 다르다. 즐겨찾기는 나만 보는 목록이고, 추천은
 * 이 레시피를 다른 사람에게 밀어주는 행동이다. 누적 수가 쌓이면 홈의 "많이 추천한
 * 메뉴"에 오르고, 유저가 등록한 레시피는 이 수가 기준을 넘어야 다른 사람의 추천
 * 후보가 된다.
 *
 * 그래서 버튼에 누적 수를 함께 보여준다. 내 행동이 어디에 쓰이는지 안 보이면 누를 이유가
 * 없다 - V2에서 좋아요가 1,148개 레시피에 4개뿐이었던 이유 중 하나로 본다.
 *
 * 로그인하지 않았으면 아무것도 그리지 않는다. 지금 상태를 묻는 엔드포인트가 본인
 * 확인을 요구해서 누적 수만 따로 받아올 방법이 없다. 로그인 안 한 사람에게도 인기가
 * 보이는 자리는 홈의 "많이 추천한 메뉴" 줄이다.
 */
export default function RecommendButton({ recipeId }: { recipeId: number }) {
  const { userId, isAuthenticated } = useAuth()
  const [status, setStatus] = useState<{ liked: boolean; count: number } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loadError, setLoadError] = useState(false)
  const [retry, setRetry] = useState(0)
  const [isBusy, setIsBusy] = useState(false)
  const pending = useRef(false)
  const generation = useRef(0)

  useEffect(() => {
    generation.current += 1
    pending.current = false
    setIsBusy(false)
    setStatus(null)
    setLoadError(false)
    setError(null)
    if (userId === null) {
      setStatus(null)
      return
    }
    const controller = new AbortController()
    getLikeStatus(recipeId, userId, controller.signal)
      .then((res) => {
        if (!controller.signal.aborted) setStatus({ liked: res.liked, count: res.like_count })
      })
      .catch(() => {
        if (!controller.signal.aborted) setLoadError(true)
      })
    return () => controller.abort()
  }, [recipeId, userId, retry])

  if (!isAuthenticated) return null
  const isLoading = status === null && !loadError

  async function handleToggle() {
    if (userId === null || status === null || pending.current) return
    pending.current = true
    setIsBusy(true)
    const requestGeneration = generation.current
    const next = status.liked
      ? { liked: false, count: Math.max(status.count - 1, 0) }
      : { liked: true, count: status.count + 1 }
    setStatus(next)
    setError(null)
    try {
      const res = await toggleLike(recipeId, userId)
      if (requestGeneration !== generation.current) return
      // 누적 수는 다른 사람도 바꾸므로 서버 값을 최종으로 삼는다.
      setStatus({ liked: res.liked, count: res.like_count })
    } catch {
      if (requestGeneration !== generation.current) return
      setStatus(status)
      setError('추천하지 못했어요. 잠시 후 다시 시도해주세요.')
    } finally {
      if (requestGeneration === generation.current) {
        pending.current = false
        setIsBusy(false)
      }
    }
  }

  return (
    <>
      <button
        className={status?.liked ? `${styles.button} ${styles.on}` : styles.button}
        type="button"
        aria-pressed={status?.liked}
        aria-busy={isBusy || isLoading}
        aria-disabled={isLoading || isBusy}
        disabled={isBusy}
        onClick={() => {
          if (loadError) {
            setLoadError(false)
            setRetry((value) => value + 1)
          } else void handleToggle()
        }}
      >
        {status !== null ? <>
          <span aria-hidden="true">{status.liked ? '♥' : '♡'}</span>
          {status.liked ? '추천함' : '추천하기'}
          <span className={styles.count}>{status.count}</span>
        </> : loadError ? '추천 상태 다시 불러오기' : '추천 상태 불러오는 중…'}
      </button>
      {isLoading && <p className="sr-only" role="status">추천 상태를 불러오는 중…</p>}
      {loadError && <p className={styles.error} role="alert">추천 상태를 불러오지 못했어요.</p>}
      {error !== null && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}
    </>
  )
}
