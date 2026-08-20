import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { ApiError, TimeoutError, toHttps } from '../api/client'
import { deleteBrag, listBrags, toggleBragLike, type BragItem } from '../api/brags'
import { getProfile } from '../api/profile'
import { useAuth } from '../auth/context'
import { useSlowRequestHint } from '../hooks/useSlowRequestHint'
import styles from './BragPage.module.css'

const PAGE_SIZE = 20

function describe(caught: unknown): string {
  if (caught instanceof ApiError || caught instanceof TimeoutError) return caught.message
  return '자랑 글을 불러오지 못했어요. 잠시 후 다시 시도해주세요.'
}

/**
 * 자랑하기 - 이 서비스로 만들어본 결과를 올리고 서로 좋아요를 누른다.
 *
 * 좋아요는 그 글이 고른 레시피의 추천에도 반영된다. 그래서 카드에 레시피 이름을
 * 링크로 함께 둔다 - 사진이 좋아 보이면 바로 그 레시피로 넘어가는 게 이 탭의 목적이다.
 */
export default function BragPage() {
  const { userId } = useAuth()

  const [brags, setBrags] = useState<BragItem[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [isLoadingMore, setIsLoadingMore] = useState(false)
  const [hasMore, setHasMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // 피드 응답은 글쓴이의 username만 준다. "내 글인가"를 판단하려면 내 username이
  // 필요한데, 카드마다 물으면 20장에 요청 20번이 된다. 한 번만 받아 둔다.
  const [myUsername, setMyUsername] = useState<string | null>(null)
  const isSlow = useSlowRequestHint(isLoading)

  useEffect(() => {
    if (userId === null) return
    const controller = new AbortController()
    getProfile(userId, controller.signal)
      .then((profile) => setMyUsername(profile.username ?? null))
      // 못 받으면 삭제 버튼만 안 보인다. 피드 자체는 멀쩡하다.
      .catch(() => {})
    return () => controller.abort()
  }, [userId])

  const load = useCallback(async (signal?: AbortSignal) => {
    try {
      const items = await listBrags({ limit: PAGE_SIZE }, signal)
      setBrags(items)
      setHasMore(items.length === PAGE_SIZE)
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
    try {
      const items = await listBrags({ limit: PAGE_SIZE, offset: brags.length })
      // offset은 첫 쪽을 받은 시점의 개수다. 그 사이 누가 글을 올리면 목록이 밀려서
      // 같은 글이 두 번 온다. 그러면 React key가 겹쳐 화면이 어긋나므로 걸러낸다.
      setBrags((prev) => {
        const seen = new Set(prev.map((b) => b.id))
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
    if (userId === null) return
    // 무료 서버에서 왕복이 2초 넘게 걸린다. 그동안 그대로면 안 눌린 줄 알고 또 누른다.
    const next = brag.liked_by_me
      ? { liked_by_me: false, like_count: Math.max(brag.like_count - 1, 0) }
      : { liked_by_me: true, like_count: brag.like_count + 1 }
    setBrags((prev) => prev.map((b) => (b.id === brag.id ? { ...b, ...next } : b)))
    try {
      const res = await toggleBragLike(brag.id, userId)
      setBrags((prev) =>
        prev.map((b) =>
          b.id === brag.id ? { ...b, liked_by_me: res.liked, like_count: res.like_count } : b,
        ),
      )
    } catch {
      setBrags((prev) => prev.map((b) => (b.id === brag.id ? brag : b)))
      setError('좋아요를 누르지 못했어요. 잠시 후 다시 시도해주세요.')
    }
  }

  async function handleDelete(brag: BragItem) {
    if (userId === null) return
    try {
      await deleteBrag(brag.id, userId)
      setBrags((prev) => prev.filter((b) => b.id !== brag.id))
    } catch (caught) {
      setError(describe(caught))
    }
  }

  return (
    <div className={styles.page}>
      <header className={styles.head}>
        <h1>자랑하기</h1>
        <Link className={styles.write} to="/brags/new">
          글쓰기
        </Link>
      </header>

      {error !== null && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}

      {isSlow && (
        <p className={styles.notice} role="status">
          <span aria-hidden="true">☕</span>
          <span>
            서버를 깨우는 중이에요
            <small>무료 서버라 첫 요청은 30초쯤 걸려요.</small>
          </span>
        </p>
      )}

      {isLoading ? (
        <ul className={styles.list} aria-hidden="true">
          {Array.from({ length: 2 }, (_, index) => (
            <li key={index} className={styles.skeleton} />
          ))}
        </ul>
      ) : brags.length === 0 ? (
        <p className={styles.empty}>
          아직 올라온 자랑이 없어요.
          <br />
          만들어보셨다면 첫 자랑을 올려주세요.
        </p>
      ) : (
        <ul className={styles.list}>
          {brags.map((brag) => (
            <li key={brag.id} className={styles.card}>
              <div className={styles.cardHead}>
                <span className={styles.author}>{brag.username}</span>
                <span className={styles.date}>{brag.created_at.slice(0, 10)}</span>
              </div>

              {brag.image_url && (
                <img
                  className={styles.photo}
                  src={toHttps(brag.image_url) ?? ''}
                  alt={`${brag.username}님이 만든 ${brag.menu_name}`}
                  loading="lazy"
                />
              )}

              <p className={styles.body}>{brag.body}</p>

              {/* 사진이 좋아 보이면 바로 그 레시피로 넘어가는 게 이 탭의 목적이다. */}
              <Link className={styles.recipe} to={`/recipe/${brag.recipe_id}`}>
                <span aria-hidden="true">🍽️</span> {brag.menu_name} 레시피 보기
              </Link>

              <div className={styles.actions}>
                {/* 이 화면은 로그인해야 열린다(AppLayout이 관문). 그래서 비로그인용
                    표시는 두지 않는다 - 서버는 피드를 공개로 열어두지만, 지금 그
                    경로로 들어올 화면이 없다. 레시피 상세에 자랑 글을 붙이게 되면
                    그때 다시 만든다. */}
                <button
                  className={brag.liked_by_me ? `${styles.like} ${styles.liked}` : styles.like}
                  type="button"
                  aria-pressed={brag.liked_by_me}
                  onClick={() => void handleLike(brag)}
                >
                  <span aria-hidden="true">{brag.liked_by_me ? '♥' : '♡'}</span>
                  좋아요
                  <span className={styles.count}>{brag.like_count}</span>
                </button>

                {/* 내 글일 때만 삭제를 보여준다. 서버도 user_id를 대조해 다시 막지만,
                    버튼이 보이는데 눌러야 실패를 아는 것은 나쁜 안내다. */}
                {myUsername !== null && myUsername === brag.username && (
                  <button
                    className={styles.delete}
                    type="button"
                    onClick={() => {
                      if (window.confirm('이 글을 삭제할까요? 되돌릴 수 없어요.')) {
                        void handleDelete(brag)
                      }
                    }}
                  >
                    삭제
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}

      {hasMore && !isLoading && (
        <button className={styles.more} type="button" onClick={loadMore} disabled={isLoadingMore}>
          {isLoadingMore ? '불러오는 중…' : '더 보기'}
        </button>
      )}
    </div>
  )
}

