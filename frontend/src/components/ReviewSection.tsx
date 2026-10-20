import { useEffect, useRef, useState } from 'react'

import { createReview, listReviews, type ReviewItem } from '../api/reviews'
import { useAuth } from '../auth/context'
import { useDeferredFocus } from '../hooks/비동기초점'
import styles from './ReviewSection.module.css'

const RATINGS = [5, 4, 3, 2, 1]

/**
 * 후기 - 실제로 만들어본 사람만 쓸 수 있는 유일한 정보.
 *
 * 목록은 로그인 없이도 읽힌다. 상세 화면이 링크로 공유되는 공개 화면이고, 링크를 받은
 * 사람에게 "다른 사람이 해보니 어땠는지"는 가장 궁금한 정보이기 때문이다. 쓰는 것만
 * 로그인을 요구한다.
 *
 * AI 요약(GET /reviews/{id}/summary)은 일부러 안 부른다. 호출마다 비용이 붙는데
 * 지금은 요약할 후기 자체가 없다(2026-08-19 기준 전체 1개). 후기가 쌓이면 켠다.
 */
export default function ReviewSection({ recipeId }: { recipeId: number }) {
  const { userId, isAuthenticated } = useAuth()
  const [reviews, setReviews] = useState<ReviewItem[] | null>(null)
  const [rating, setRating] = useState(5)
  const [text, setText] = useState('')
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [retry, setRetry] = useState(0)
  const saving = useRef(false)
  const { capture } = useDeferredFocus()
  const retryFocus = useRef<(() => boolean) | null>(null)
  const headingRef = useRef<HTMLHeadingElement>(null)
  const retryButtonRef = useRef<HTMLButtonElement>(null)

  useEffect(() => { retryFocus.current = null }, [recipeId])

  useEffect(() => {
    setReviews(null)
    setLoadError(null)
    const controller = new AbortController()
    listReviews(recipeId, controller.signal)
      .then((rows) => {
        if (!Array.isArray(rows)) throw new Error('후기 목록 형식 오류')
        if (!controller.signal.aborted) setReviews(rows)
      })
      .catch(() => {
        if (!controller.signal.aborted) setLoadError('후기를 불러오지 못했어요.')
      })
    return () => controller.abort()
  }, [recipeId, retry])

  useEffect(() => {
    if (reviews === null && loadError === null) return
    const canRestore = retryFocus.current
    retryFocus.current = null
    if (canRestore?.()) {
      const target = loadError === null ? headingRef.current : retryButtonRef.current
      target?.focus({ preventScroll: true })
    }
  }, [reviews, loadError])

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    if (userId === null || text.trim() === '' || saving.current) return
    saving.current = true
    setIsSaving(true)
    setError(null)
    try {
      await createReview(recipeId, userId, rating, text.trim())
      setText('')
      try {
        const rows = await listReviews(recipeId)
        if (!Array.isArray(rows)) throw new Error('후기 목록 형식 오류')
        setReviews(rows)
        setLoadError(null)
      } catch {
        setLoadError('후기는 저장했지만 목록을 새로 불러오지 못했어요.')
      }
    } catch {
      setError('후기를 남기지 못했어요. 잠시 후 다시 시도해주세요.')
    } finally {
      saving.current = false
      setIsSaving(false)
    }
  }

  return (
    <section className={styles.section} aria-labelledby="review-heading">
      <div className={styles.head}>
        <h2 id="review-heading" ref={headingRef} tabIndex={-1}>후기</h2>
        {reviews !== null && reviews.length > 0 && <span>{reviews.length}개</span>}
      </div>

      {isAuthenticated ? (
        <form className={styles.form} onSubmit={(event) => void handleSubmit(event)}>
          <label className={styles.ratingLabel} htmlFor="review-rating">
            별점
          </label>
          <select
            id="review-rating"
            className={styles.rating}
            value={rating}
            onChange={(event) => setRating(Number(event.target.value))}
          >
            {RATINGS.map((value) => (
              <option key={value} value={value}>
                {'★'.repeat(value)} {value}점
              </option>
            ))}
          </select>
          <label className={styles.textLabel} htmlFor="review-text">
            만들어본 후기
          </label>
          <textarea
            id="review-text"
            className={styles.text}
            value={text}
            rows={3}
            maxLength={500}
            placeholder="간은 어땠는지, 무엇을 바꿔봤는지 적어주세요."
            onChange={(event) => setText(event.target.value)}
          />
          {/* 빈 후기를 막는다. 별점만 남기면 다음 사람에게 아무 정보도 안 된다. */}
          <button className={styles.submit} type="submit" disabled={isSaving || text.trim() === ''}>
            {isSaving ? '남기는 중…' : '후기 남기기'}
          </button>
          {error !== null && (
            <p className={styles.error} role="alert">
              {error}
            </p>
          )}
        </form>
      ) : (
        <p className={styles.empty}>후기를 남기려면 로그인이 필요해요.</p>
      )}

      {loadError !== null ? (
        <div className={styles.loadState}>
          <p role="alert">{loadError}</p>
          <button ref={retryButtonRef} className={styles.retry} type="button" onClick={() => {
            retryFocus.current = capture()
            setRetry((value) => value + 1)
          }}>후기 다시 불러오기</button>
        </div>
      ) : reviews === null ? (
        <p className={styles.empty} role="status">후기를 불러오는 중…</p>
      ) : reviews.length === 0 ? (
        <p className={styles.empty}>아직 후기가 없어요. 만들어보셨다면 첫 후기를 남겨주세요.</p>
      ) : (
        <ul className={styles.list}>
          {reviews.map((review, index) => (
            <li key={`${review.username}-${review.created_at}-${index}`}>
              <div className={styles.itemHead}>
                <span className={styles.stars} aria-label={`별점 ${review.rating}점`}>
                  <span aria-hidden="true">{'★'.repeat(review.rating)}</span>
                </span>
                <span className={styles.author}>{review.username}</span>
                <span className={styles.date}>{review.created_at.slice(0, 10)}</span>
              </div>
              <p className={styles.body}>{review.review_text}</p>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
