import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'

import { ApiError, TimeoutError } from '../api/client'
import {
  createFeedback,
  deleteFeedback,
  listAllFeedback,
  listMyFeedback,
  type FeedbackItem,
} from '../api/feedback'
import { getProfile } from '../api/profile'
import { useAuth } from '../auth/context'
import styles from './FeedbackPage.module.css'

/** 무엇을 적어야 할지 모르면 아무도 안 쓴다. 초대 페이지에서 물은 것과 같은 넷이다. */
const PROMPTS = [
  '어디서 “뭐 어쩌라는 거지” 싶었는지',
  '추천받은 메뉴가 해먹을 만했는지, 아니면 왜 아니었는지',
  '재료 넣는 게 귀찮았는지',
  '안 쓰게 됐다면 며칠째에 그랬는지',
]

function describe(caught: unknown, fallback = '보내지 못했어요. 잠시 후 다시 시도해주세요.'): string {
  if (caught instanceof ApiError || caught instanceof TimeoutError) return caught.message
  return fallback
}

type LoadState = 'loading' | 'loaded' | 'error'

/**
 * 피드백 - "이 앱 어땠어요"를 앱 안에서 받는다.
 *
 * 쓴 사람은 자기 글만 본다. 지인 테스트에서 남의 의견이 보이면 그쪽으로 끌려가서,
 * 두 번째 사람부터는 자기 생각이 아니라 "나도 그랬어"를 쓰게 된다. 관리자에게만
 * 전체 목록을 함께 보여준다.
 */
export default function FeedbackPage() {
  const { userId, isAuthenticated } = useAuth()

  const [mine, setMine] = useState<FeedbackItem[]>([])
  const [all, setAll] = useState<FeedbackItem[] | null>(null)
  const [mineState, setMineState] = useState<LoadState>('loading')
  const [mineError, setMineError] = useState<string | null>(null)
  const [allState, setAllState] = useState<LoadState>('loading')
  const [allError, setAllError] = useState<string | null>(null)
  const [isAdmin, setIsAdmin] = useState(false)
  const [body, setBody] = useState('')
  const [isSending, setIsSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sent, setSent] = useState(false)
  const [deletingId, setDeletingId] = useState<number | null>(null)
  const [deleteStatus, setDeleteStatus] = useState('')
  const bodyInput = useRef<HTMLTextAreaElement>(null)
  const mineHeading = useRef<HTMLHeadingElement>(null)
  const allHeading = useRef<HTMLHeadingElement>(null)
  const interactionVersion = useRef(0)
  const mineRetryFocus = useRef<number | null>(null)
  const allRetryFocus = useRef<number | null>(null)
  const deleteButtons = useRef(new Map<number, HTMLButtonElement>())
  const pendingFocus = useRef<{ target: number | 'input'; version: number } | null>(null)
  const deleteLock = useRef<number | null>(null)
  const sendLock = useRef(false)
  const mineRequest = useRef<AbortController | null>(null)
  const allRequest = useRef<AbortController | null>(null)
  const localAdded = useRef(new Map<number, FeedbackItem>())
  const localDeleted = useRef(new Set<number>())

  useEffect(() => {
    // 요청을 기다리는 동안 사용자가 다른 일을 시작했다면 자동 초점 복귀보다 우선한다.
    const markInteraction = () => { interactionVersion.current += 1 }
    document.addEventListener('pointerdown', markInteraction, true)
    document.addEventListener('keydown', markInteraction, true)
    document.addEventListener('focusin', markInteraction, true)
    return () => {
      document.removeEventListener('pointerdown', markInteraction, true)
      document.removeEventListener('keydown', markInteraction, true)
      document.removeEventListener('focusin', markInteraction, true)
    }
  }, [])

  const loadMine = useCallback(async () => {
    if (userId === null) return
    mineRequest.current?.abort()
    const controller = new AbortController()
    mineRequest.current = controller
    setMineState('loading')
    setMineError(null)
    try {
      const rows = await listMyFeedback(userId, controller.signal)
      if (controller.signal.aborted) return
      // 조회를 기다리는 동안 작성·삭제한 의견이 늦게 온 응답에 되돌아가지 않도록 한다.
      const fetchedIds = new Set(rows.map((item) => item.id))
      const added = [...localAdded.current.values()].filter((item) => !fetchedIds.has(item.id)).reverse()
      setMine([...added, ...rows].filter((item) => !localDeleted.current.has(item.id)))
      setMineState('loaded')
    } catch (caught) {
      if (controller.signal.aborted) return
      setMineError(describe(caught, '내가 보낸 말을 불러오지 못했어요. 다시 시도해주세요.'))
      setMineState('error')
    }
  }, [userId])

  const loadAll = useCallback(async () => {
    if (userId === null) return
    allRequest.current?.abort()
    const controller = new AbortController()
    allRequest.current = controller
    setAllState('loading')
    setAllError(null)
    let checkingPermission = true
    try {
      // 권한은 프로필과 서버에서 확인하며, 일반 계정에는 전체 목록을 요청하지 않는다.
      const profile = await getProfile(userId, controller.signal)
      if (controller.signal.aborted) return
      setIsAdmin(profile.is_admin)
      checkingPermission = false
      if (!profile.is_admin) {
        setAll(null)
        setAllState('loaded')
        return
      }
      const rows = await listAllFeedback(userId, controller.signal)
      if (controller.signal.aborted) return
      setAll(rows.filter((item) => !localDeleted.current.has(item.id)))
      setAllState('loaded')
    } catch (caught) {
      if (controller.signal.aborted) return
      setAllError(checkingPermission
        ? '계정 권한을 확인하지 못했어요. 내가 보낸 말과 의견 보내기는 계속 이용할 수 있어요.'
        : describe(caught, '전체 의견을 불러오지 못했어요. 다시 시도해주세요.'))
      setAllState('error')
    }
  }, [userId])

  useEffect(() => {
    void loadMine()
    void loadAll()
    return () => {
      mineRequest.current?.abort()
      allRequest.current?.abort()
    }
  }, [loadMine, loadAll])

  useLayoutEffect(() => {
    if (pendingFocus.current === null || deletingId !== null) return
    const pending = pendingFocus.current
    pendingFocus.current = null
    if (pending.version !== interactionVersion.current) return
    const target = pending.target === 'input'
      ? bodyInput.current
      : deleteButtons.current.get(pending.target) ?? bodyInput.current
    target?.focus()
  }, [mine, deletingId])

  useLayoutEffect(() => {
    if (mineRetryFocus.current !== null && mineState !== 'loading') {
      const shouldFocus = mineRetryFocus.current === interactionVersion.current
      mineRetryFocus.current = null
      if (shouldFocus) mineHeading.current?.focus()
    }
    if (allRetryFocus.current !== null && allState !== 'loading') {
      const shouldFocus = allRetryFocus.current === interactionVersion.current
      allRetryFocus.current = null
      if (shouldFocus) (allHeading.current ?? bodyInput.current)?.focus()
    }
  }, [mineState, allState])

  if (!isAuthenticated) {
    return (
      <div className={styles.guest}>
        <h1>하고 싶은 말</h1>
        <p>로그인하면 의견을 남길 수 있어요.</p>
        <Link className={styles.primary} to="/login">
          로그인하러 가기
        </Link>
      </div>
    )
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    if (userId === null || body.trim() === '' || sendLock.current) return
    sendLock.current = true
    setIsSending(true)
    setError(null)
    try {
      const item = await createFeedback(userId, body.trim())
      localAdded.current.set(item.id, item)
      setMine((prev) => [item, ...prev])
      setBody('')
      setSent(true)
    } catch (caught) {
      setError(describe(caught))
    } finally {
      sendLock.current = false
      setIsSending(false)
    }
  }

  async function handleDelete(item: FeedbackItem) {
    if (userId === null || deleteLock.current !== null) return
    if (!window.confirm('이 글을 지울까요?')) return
    const focusVersion = interactionVersion.current
    deleteLock.current = item.id
    setDeletingId(item.id)
    setError(null)
    setDeleteStatus('')
    try {
      await deleteFeedback(item.id, userId)
      localDeleted.current.add(item.id)
      localAdded.current.delete(item.id)
      const index = mine.findIndex((row) => row.id === item.id)
      pendingFocus.current = {
        target: mine[index + 1]?.id ?? mine[index - 1]?.id ?? 'input',
        version: focusVersion,
      }
      setMine((prev) => prev.filter((f) => f.id !== item.id))
      setAll((prev) => prev?.filter((f) => f.id !== item.id) ?? null)
      setDeleteStatus('의견을 지웠어요.')
    } catch (caught) {
      setError(describe(caught, '의견을 지우지 못했어요. 다시 시도해주세요.'))
      pendingFocus.current = { target: item.id, version: focusVersion }
    } finally {
      deleteLock.current = null
      setDeletingId(null)
    }
  }

  return (
    <div className={styles.page}>
      <h1>하고 싶은 말</h1>
      <p className={styles.lead}>
        좋았던 것보다 <strong>불편했던 것</strong>이 훨씬 도움이 돼요.
        만든 사람만 읽고, 다른 사람에게는 안 보여요.
      </p>

      {error !== null && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}

      <form className={styles.form} onSubmit={(event) => void handleSubmit(event)}>
        <label className={styles.label} htmlFor="feedback-body">
          이런 게 궁금해요
        </label>
        <ul className={styles.prompts}>
          {PROMPTS.map((prompt) => (
            <li key={prompt}>{prompt}</li>
          ))}
        </ul>
        <textarea
          id="feedback-body"
          ref={bodyInput}
          className={styles.textarea}
          rows={6}
          maxLength={2000}
          value={body}
          placeholder="짧아도 괜찮아요. 생각난 김에 적어주세요."
          onChange={(event) => {
            setBody(event.target.value)
            setSent(false)
          }}
        />
        <button className={styles.primary} type="submit" disabled={isSending || body.trim() === ''}>
          {isSending ? '보내는 중…' : '보내기'}
        </button>
        {sent && (
          <p className={styles.thanks} role="status">
            고맙습니다. 잘 읽을게요.
          </p>
        )}
      </form>

      <section className={styles.section} aria-labelledby="mine-heading">
        <h2 id="mine-heading" ref={mineHeading} tabIndex={-1}>내가 보낸 말</h2>
        {mineState === 'loading' && <p className={styles.empty} role="status">내가 보낸 말을 불러오는 중이에요.</p>}
        {mineState === 'error' && (
          <div className={styles.error}>
            <p role="alert">{mineError}</p>
            <button className={styles.retry} type="button" onClick={() => { mineRetryFocus.current = interactionVersion.current; void loadMine() }}>내 의견 다시 불러오기</button>
          </div>
        )}
        <p className="sr-only" role="status">{deleteStatus}</p>
        {mineState === 'loaded' && mine.length === 0 && (
          <p className={styles.empty}>아직 없어요.</p>
        )}
        {mine.length > 0 && (
          <ul className={styles.list} aria-busy={mineState === 'loading'}>
            {mine.map((item, index) => (
              <li key={item.id}>
                <p className={styles.body}>{item.body}</p>
                <div className={styles.itemFoot}>
                  <span className={styles.date}>{item.created_at.slice(0, 10)}</span>
                  <button
                    ref={(element) => { if (element) deleteButtons.current.set(item.id, element); else deleteButtons.current.delete(item.id) }}
                    className={styles.delete}
                    type="button"
                    aria-label={`${index + 1}번째 의견: ${item.body.slice(0, 30)}${item.body.length > 30 ? '…' : ''} 지우기`}
                    disabled={deletingId !== null}
                    onClick={() => void handleDelete(item)}
                  >
                    {deletingId === item.id ? '지우는 중…' : '지우기'}
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* 관리자에게만 보인다. 서버가 403으로 다시 막으므로 여기는 편의일 뿐이다. */}
      {(isAdmin || allError !== null) && (
        <section className={styles.section} aria-labelledby="all-heading">
          <h2 id="all-heading" ref={allHeading} tabIndex={-1}>{isAdmin ? `전체 의견${allState === 'loaded' ? ` (${all?.length ?? 0})` : ''}` : '계정 권한 확인'}</h2>
          {isAdmin && <p className={styles.empty}>
            관리자에게만 보여요. 누가 썼는지는 그 사람의 사용 기록과 맞춰 보려고 함께 둡니다.
          </p>}
          {allState === 'loading' && <p className={styles.empty} role="status">전체 의견을 불러오는 중이에요.</p>}
          {allState === 'error' && (
            <div className={styles.error}>
              <p role="alert">{allError}</p>
              <button className={styles.retry} type="button" onClick={() => { allRetryFocus.current = interactionVersion.current; void loadAll() }}>전체 의견 다시 확인하기</button>
            </div>
          )}
          {allState === 'loaded' && all?.length === 0 && <p className={styles.empty}>아직 등록된 의견이 없어요.</p>}
          {all !== null && all.length > 0 && (
            <ul className={styles.list} aria-busy={allState === 'loading'}>
              {all.map((item) => (
                <li key={item.id}>
                  <p className={styles.body}>{item.body}</p>
                  <div className={styles.itemFoot}>
                    <span className={styles.who}>{item.username}</span>
                    <span className={styles.date}>{item.created_at.slice(0, 10)}</span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </div>
  )
}
