import { useEffect, useState } from 'react'
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

function describe(caught: unknown): string {
  if (caught instanceof ApiError || caught instanceof TimeoutError) return caught.message
  return '보내지 못했어요. 잠시 후 다시 시도해주세요.'
}

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
  const [body, setBody] = useState('')
  const [isSending, setIsSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sent, setSent] = useState(false)

  useEffect(() => {
    if (userId === null) return
    const controller = new AbortController()

    listMyFeedback(userId, controller.signal)
      .then(setMine)
      .catch((caught: unknown) => {
        if (!controller.signal.aborted) setError(describe(caught))
      })

    // 관리자인지 화면이 판단하지 않는다. 프로필이 알려주고, 서버가 다시 막는다.
    getProfile(userId, controller.signal)
      .then((profile) => {
        if (!profile.is_admin) return
        return listAllFeedback(userId, controller.signal).then(setAll)
      })
      .catch(() => {})

    return () => controller.abort()
  }, [userId])

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
    if (userId === null || body.trim() === '') return
    setIsSending(true)
    setError(null)
    try {
      const item = await createFeedback(userId, body.trim())
      setMine((prev) => [item, ...prev])
      setBody('')
      setSent(true)
    } catch (caught) {
      setError(describe(caught))
    } finally {
      setIsSending(false)
    }
  }

  async function handleDelete(item: FeedbackItem) {
    if (userId === null) return
    try {
      await deleteFeedback(item.id, userId)
      setMine((prev) => prev.filter((f) => f.id !== item.id))
    } catch (caught) {
      setError(describe(caught))
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
        <h2 id="mine-heading">내가 보낸 말</h2>
        {mine.length === 0 ? (
          <p className={styles.empty}>아직 없어요.</p>
        ) : (
          <ul className={styles.list}>
            {mine.map((item) => (
              <li key={item.id}>
                <p className={styles.body}>{item.body}</p>
                <div className={styles.itemFoot}>
                  <span className={styles.date}>{item.created_at.slice(0, 10)}</span>
                  <button
                    className={styles.delete}
                    type="button"
                    onClick={() => {
                      if (window.confirm('이 글을 지울까요?')) void handleDelete(item)
                    }}
                  >
                    지우기
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* 관리자에게만 보인다. 서버가 403으로 다시 막으므로 여기는 편의일 뿐이다. */}
      {all !== null && (
        <section className={styles.section} aria-labelledby="all-heading">
          <h2 id="all-heading">전체 ({all.length})</h2>
          <p className={styles.empty}>
            관리자에게만 보여요. 누가 썼는지는 그 사람의 사용 기록과 맞춰 보려고 함께 둡니다.
          </p>
          {all.length > 0 && (
            <ul className={styles.list}>
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
