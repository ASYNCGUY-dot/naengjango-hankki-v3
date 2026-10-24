import { useId } from 'react'

import { useAuth } from '../auth/context'
import { useFavorites } from '../favorites/context'
import Icon from './아이콘'
import styles from './FavoriteButton.module.css'

/** 즐겨찾기는 개인 저장용 별이다. 공개 추천의 하트와 구분한다. */
export default function FavoriteButton({
  recipeId,
  recipeName,
  variant = 'text',
}: {
  recipeId: number
  recipeName?: string
  variant?: 'text' | 'icon'
}) {
  const { isAuthenticated } = useAuth()
  const { isReady, loadError, favoriteIds, busyIds, errors, retry, toggle } = useFavorites()
  const feedbackId = useId()
  if (!isAuthenticated) return null

  const isFavorited = favoriteIds.has(recipeId)
  const isBusy = busyIds.has(recipeId)
  const isLoading = !isReady && !loadError
  const error = loadError ? '즐겨찾기 상태를 불러오지 못했어요.' : errors.get(recipeId)
  const isIcon = variant === 'icon'
  const action = isReady ? (isFavorited ? '즐겨찾기 해제' : '즐겨찾기 추가')
    : loadError ? '즐겨찾기 다시 불러오기' : '즐겨찾기 불러오는 중'
  const label = recipeName ? `${action}: ${recipeName}` : action
  const className = [styles.button, isReady && isFavorited && styles.on, isIcon && styles.icon]
    .filter(Boolean).join(' ')

  return (
    <>
      <button
        className={className}
        type="button"
        title={isIcon ? label : undefined}
        aria-label={isIcon ? label : undefined}
        aria-pressed={isReady ? isFavorited : undefined}
        aria-busy={isBusy || isLoading}
        aria-disabled={isLoading || isBusy}
        aria-describedby={error ? feedbackId : undefined}
        disabled={isBusy}
        onClick={() => {
          if (loadError) retry()
          else if (isReady && !isBusy) void toggle(recipeId)
        }}
      >
        {isIcon ? (
          isReady ? <Icon name="star" size={24} fill={isFavorited ? 'currentColor' : 'none'} />
            : <span aria-hidden="true">{loadError ? '!' : '…'}</span>
        ) : isReady ? <>
          <span aria-hidden="true">{isFavorited ? '★' : '☆'}</span>
          {isFavorited ? '즐겨찾기됨' : '즐겨찾기'}
        </> : loadError ? '즐겨찾기 다시 불러오기' : '즐겨찾기 불러오는 중…'}
      </button>
      {isLoading && <p className="sr-only" role="status">즐겨찾기 상태를 불러오는 중…</p>}
      {error && <p id={feedbackId} className={styles.error} role="alert">{error}</p>}
    </>
  )
}
