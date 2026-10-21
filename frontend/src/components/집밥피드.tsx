import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'

import { ApiError, TimeoutError, toHttps } from '../api/client'
import { deleteBrag, listBrags, toggleBragLike, type BragItem } from '../api/brags'
import { getProfile } from '../api/profile'
import { useAuth } from '../auth/context'
import { useSlowRequestHint } from '../hooks/useSlowRequestHint'
import { useDeferredFocus } from '../hooks/비동기초점'
import Icon from './아이콘'
import styles from './집밥피드.module.css'

const PAGE_SIZE = 20

function describe(caught: unknown): string {
  if (caught instanceof ApiError || caught instanceof TimeoutError) return caught.message
  return '자랑 글을 불러오지 못했어요. 잠시 후 다시 시도해주세요.'
}

function FeedCard({
  brag,
  isMine,
  isLiking,
  onLike,
  onDelete,
  reading,
}: {
  brag: BragItem
  isMine: boolean
  isLiking: boolean
  onLike: () => void
  onDelete: () => void
  reading: boolean
}) {
  const [failedImage, setFailedImage] = useState<string | null>(null)
  const [isExpanded, setIsExpanded] = useState(false)
  const [canExpand, setCanExpand] = useState(false)
  const bodyRef = useRef<HTMLParagraphElement>(null)
  const bodyId = `집밥글-${brag.id}`
  const imageUrl = toHttps(brag.image_url)

  useLayoutEffect(() => {
    const body = bodyRef.current
    if (typeof window === 'undefined' || body === null || isExpanded || reading) return
    let active = true
    const measureOverflow = () => {
      if (active) setCanExpand(body.scrollHeight > body.clientHeight)
    }
    measureOverflow()

    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(measureOverflow)
    observer?.observe(body)
    if (body.parentElement) observer?.observe(body.parentElement)

    // 글꼴 교체는 두 줄 높이가 같아도 실제 줄바꿈 수를 바꿀 수 있다.
    const fonts = document.fonts
    void fonts?.ready.then(measureOverflow)
    fonts?.addEventListener('loadingdone', measureOverflow)
    window.addEventListener('resize', measureOverflow)
    return () => {
      active = false
      observer?.disconnect()
      fonts?.removeEventListener('loadingdone', measureOverflow)
      window.removeEventListener('resize', measureOverflow)
    }
  }, [brag.body, brag.menu_name, isExpanded, reading])

  return (
    <li className={styles.card}>
      <Link
        className={styles.photoLink}
        to={`/recipe/${brag.recipe_id}`}
        aria-label={`${brag.menu_name} 레시피 보기`}
      >
        {imageUrl && failedImage !== imageUrl ? (
          <img
            className={styles.photo}
            src={imageUrl}
            alt={`${brag.username}님이 만든 ${brag.menu_name}`}
            loading="lazy"
            onError={() => setFailedImage(imageUrl)}
          />
        ) : (
          <span className={styles.photoFallback}>
            <Icon name="bowl" size={32} />
            <span>{brag.menu_name}</span>
          </span>
        )}
        <span className={styles.recipeCaption}>레시피 보기<Icon name="chevron-right" size={16} /></span>
      </Link>

      <p ref={bodyRef} id={bodyId} className={isExpanded || reading ? `${styles.body} ${styles.expanded}` : styles.body}>
        {brag.body || brag.menu_name}
      </p>

      <div className={styles.meta}>
        <span className={styles.author} title={brag.username}>{brag.username}</span>
        <span className={styles.dot} aria-hidden="true">·</span>
        <button
          className={brag.liked_by_me ? `${styles.like} ${styles.liked}` : styles.like}
          type="button"
          aria-label={`좋아요 ${brag.like_count}`}
          aria-pressed={brag.liked_by_me}
          disabled={isLiking}
          onClick={onLike}
        >
          <Icon name="heart" size={17} />
          <span>{brag.like_count}</span>
        </button>
      </div>

      {((canExpand && !reading) || isMine) && (
        <div className={styles.actions}>
          {canExpand && !reading && (
            <button
              className={styles.expand}
              type="button"
              aria-expanded={isExpanded}
              aria-controls={bodyId}
              onClick={() => setIsExpanded((value) => !value)}
            >
              {isExpanded ? '글 접기' : '글 더보기'}
            </button>
          )}
          {isMine && (
            <button
              className={styles.delete}
              type="button"
              aria-label={`이 글 삭제: ${brag.menu_name}`}
              onClick={() => {
                if (window.confirm('이 글을 삭제할까요? 되돌릴 수 없어요.')) onDelete()
              }}
            >
              이 글 삭제
            </button>
          )}
        </div>
      )}
      {(isExpanded || reading) && (
        <time className={styles.date} dateTime={brag.created_at}>
          {brag.created_at.slice(0, 10)}
        </time>
      )}
    </li>
  )
}

/** 홈과 자랑하기에서 같은 피드·좋아요·삭제 흐름을 사용한다. */
export default function HomeFeed() {
  const { userId } = useAuth()
  const [brags, setBrags] = useState<BragItem[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [isLoadingMore, setIsLoadingMore] = useState(false)
  const [hasMore, setHasMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [myUsername, setMyUsername] = useState<string | null>(null)
  const [likingIds, setLikingIds] = useState<Set<number>>(new Set())
  const pendingLikes = useRef(new Set<number>())
  const isSlow = useSlowRequestHint(isLoading)
  const [reading, setReading] = useState(() => {
    try { return localStorage.getItem('naengjango.feed-view') === 'reading' } catch { return false }
  })
  const [status, setStatus] = useState('')
  const viewButton = useRef<HTMLButtonElement>(null)
  const pendingDeletes = useRef(new Set<number>())
  const { capture: captureFocus } = useDeferredFocus()

  function changeView(next: boolean) {
    setReading(next)
    try { localStorage.setItem('naengjango.feed-view', next ? 'reading' : 'photos') } catch { /* 저장이 막혀도 이번 보기 전환은 유지한다. */ }
  }

  useEffect(() => {
    if (userId === null) return
    const controller = new AbortController()
    getProfile(userId, controller.signal)
      .then((profile) => setMyUsername(profile.username ?? null))
      .catch(() => {})
    return () => controller.abort()
  }, [userId])

  const load = useCallback(async (signal?: AbortSignal) => {
    setIsLoading(true)
    setError(null)
    try {
      const items = await listBrags({ limit: PAGE_SIZE }, signal)
      if (signal?.aborted) return
      setBrags(items)
      setHasMore(items.length === PAGE_SIZE)
      setStatus(`집밥 글 ${items.length}개를 불러왔어요.`)
    } catch (caught) {
      if (signal?.aborted) return
      setError(describe(caught))
    } finally {
      if (!signal?.aborted) setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    void load(controller.signal)
    return () => controller.abort()
  }, [load])

  async function loadMore() {
    setIsLoadingMore(true)
    setError(null)
    try {
      const items = await listBrags({ limit: PAGE_SIZE, offset: brags.length })
      setBrags((prev) => {
        const seen = new Set(prev.map((brag) => brag.id))
        return [...prev, ...items.filter((item) => !seen.has(item.id))]
      })
      setHasMore(items.length === PAGE_SIZE)
    } catch (caught) {
      setError(describe(caught))
    } finally {
      setIsLoadingMore(false)
    }
  }

  async function handleLike(brag: BragItem) {
    if (userId === null || pendingLikes.current.has(brag.id)) return
    pendingLikes.current.add(brag.id)
    setLikingIds(new Set(pendingLikes.current))
    setError(null)
    const next = brag.liked_by_me
      ? { liked_by_me: false, like_count: Math.max(brag.like_count - 1, 0) }
      : { liked_by_me: true, like_count: brag.like_count + 1 }
    setBrags((prev) => prev.map((item) => (item.id === brag.id ? { ...item, ...next } : item)))
    try {
      const res = await toggleBragLike(brag.id, userId)
      setBrags((prev) => prev.map((item) => (
        item.id === brag.id ? { ...item, liked_by_me: res.liked, like_count: res.like_count } : item
      )))
    } catch {
      setBrags((prev) => prev.map((item) => (item.id === brag.id ? brag : item)))
      setError('좋아요를 누르지 못했어요. 잠시 후 다시 시도해주세요.')
    } finally {
      pendingLikes.current.delete(brag.id)
      setLikingIds(new Set(pendingLikes.current))
    }
  }

  async function handleDelete(brag: BragItem) {
    if (userId === null || pendingDeletes.current.has(brag.id)) return
    const canRestore = captureFocus()
    pendingDeletes.current.add(brag.id)
    try {
      await deleteBrag(brag.id, userId)
      setBrags((prev) => prev.filter((item) => item.id !== brag.id))
      setStatus('집밥 글을 삭제했어요.')
      if (canRestore()) viewButton.current?.focus()
    } catch (caught) {
      setError(describe(caught))
    } finally {
      pendingDeletes.current.delete(brag.id)
    }
  }

  return (
    <div className={styles.feed}>
      <div className={styles.viewOptions} role="group" aria-label="피드 보기 방식">
        <button ref={viewButton} type="button" aria-pressed={!reading} onClick={() => changeView(false)}>사진 모아보기</button>
        <button type="button" aria-pressed={reading} onClick={() => changeView(true)}>글 함께 읽기</button>
      </div>
      <p className="sr-only" role="status">{isLoading ? '집밥 글을 불러오는 중이에요.' : status}</p>
      {error !== null && <div className={styles.error} role="alert"><p>{error}</p><button type="button" className={styles.retry} onClick={() => void load()}>다시 불러오기</button></div>}
      {isSlow && (
        <p className={styles.notice} role="status">
          서버를 깨우는 중이에요
          <small>첫 요청은 잠시 걸릴 수 있어요.</small>
        </p>
      )}

      {isLoading ? (
        <ul className={styles.list} aria-hidden="true">
          {Array.from({ length: 6 }, (_, index) => <li key={index} className={styles.skeleton} />)}
        </ul>
      ) : brags.length === 0 && error === null ? (
        <div className={styles.empty}>
          <Icon name="bowl" size={36} />
          <p>아직 올라온 자랑이 없어요.<br />만들어보셨다면 첫 자랑을 올려주세요.</p>
          <Link to="/brags/new">첫 집밥 올리기 <Icon name="arrow-right" size={16} /></Link>
        </div>
      ) : brags.length > 0 ? (
        <ul className={reading ? `${styles.list} ${styles.reading}` : styles.list} aria-label="집밥 글" aria-busy={isLoadingMore}>
          {brags.map((brag) => (
            <FeedCard
              key={brag.id}
              brag={brag}
              reading={reading}
              isMine={myUsername !== null && myUsername === brag.username}
              isLiking={likingIds.has(brag.id)}
              onLike={() => void handleLike(brag)}
              onDelete={() => void handleDelete(brag)}
            />
          ))}
        </ul>
      ) : null}

      {hasMore && !isLoading && (
        <button className={styles.more} type="button" onClick={loadMore} disabled={isLoadingMore}>
          {isLoadingMore ? '불러오는 중…' : '더 보기'}
        </button>
      )}
    </div>
  )
}
