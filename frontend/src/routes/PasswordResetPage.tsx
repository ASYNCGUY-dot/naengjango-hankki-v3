import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'

import { MIN_PASSWORD_LENGTH, confirmPasswordReset, requestPasswordReset } from '../api/auth'
import { ApiError, TimeoutError } from '../api/client'
import { useSlowRequestHint } from '../hooks/useSlowRequestHint'
import styles from './AuthPage.module.css'

function describe(caught: unknown): string {
  if (caught instanceof ApiError || caught instanceof TimeoutError) return caught.message
  return '연결에 실패했습니다. 잠시 후 다시 시도해주세요.'
}

/**
 * 초기화 요청 화면.
 *
 * "비밀번호 찾기"가 아니다. 비밀번호는 단방향 해시로 저장돼 서버도 알 수 없으므로
 * 알려줄 방법이 없다. 새로 설정할 수 있는 링크를 보내는 것만 가능하다.
 */
export function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [isPending, setIsPending] = useState(false)
  const [isSent, setIsSent] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const isSlow = useSlowRequestHint(isPending)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (isPending) return
    setError(null)
    setIsPending(true)
    try {
      await requestPasswordReset(email.trim())
      setIsSent(true)
    } catch (caught) {
      setError(describe(caught))
    } finally {
      setIsPending(false)
    }
  }

  return (
    <main className={styles.page}>
      <div className={styles.brand}>
        <h1>비밀번호 초기화</h1>
        <p className={styles.tagline}>가입할 때 쓴 이메일로 링크를 보내드려요</p>
      </div>

      {isSlow && (
        <p className={styles.wake} role="status">
          <span aria-hidden="true">☕</span>
          <span>
            서버를 깨우는 중이에요
            <small>무료 서버라 첫 요청은 30초쯤 걸려요.</small>
          </span>
        </p>
      )}

      {error !== null && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}

      {isSent ? (
        // 서버는 가입된 주소든 아니든 같은 응답을 준다(계정 존재 여부를 숨기기 위해).
        // 그래서 "보냈습니다"가 아니라 "가입된 주소라면 갈 것"이라고 안내해야 사실과 맞다.
        <p className={styles.wake} role="status">
          <span aria-hidden="true">✉️</span>
          <span>
            가입된 이메일이라면 초기화 링크를 보냈어요
            <small>메일함을 확인해주세요. 링크는 30분 동안만 쓸 수 있어요.</small>
          </span>
        </p>
      ) : (
        <form onSubmit={handleSubmit} noValidate>
          <div className={styles.field}>
            <label htmlFor="reset-email">이메일</label>
            <input
              id="reset-email"
              type="email"
              autoComplete="email"
              placeholder="가입할 때 쓴 이메일"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <button className={styles.cta} type="submit" disabled={isPending}>
            {isPending ? '보내는 중…' : '초기화 링크 받기'}
          </button>
        </form>
      )}

      <p className={styles.foot}>
        <Link to="/login">로그인으로 돌아가기</Link>
      </p>
    </main>
  )
}

/** 메일의 링크로 들어오는 화면. 주소의 token으로 새 비밀번호를 설정한다. */
export function ResetPasswordPage() {
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token') ?? ''
  const navigate = useNavigate()

  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [isPending, setIsPending] = useState(false)
  const [isDone, setIsDone] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const isSlow = useSlowRequestHint(isPending)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (isPending) return
    setError(null)

    if (password.length < MIN_PASSWORD_LENGTH) {
      setError(`비밀번호는 ${MIN_PASSWORD_LENGTH}자 이상이어야 합니다.`)
      return
    }
    if (password !== confirm) {
      setError('두 비밀번호가 다릅니다.')
      return
    }

    setIsPending(true)
    try {
      await confirmPasswordReset(token, password)
      setIsDone(true)
    } catch (caught) {
      setError(describe(caught))
    } finally {
      setIsPending(false)
    }
  }

  if (token === '') {
    return (
      <main className={styles.page}>
        <div className={styles.brand}>
          <h1>비밀번호 초기화</h1>
        </div>
        <p className={styles.error} role="alert">
          링크가 올바르지 않습니다. 초기화를 다시 요청해주세요.
        </p>
        <p className={styles.foot}>
          <Link to="/forgot-password">초기화 다시 요청하기</Link>
        </p>
      </main>
    )
  }

  return (
    <main className={styles.page}>
      <div className={styles.brand}>
        <h1>새 비밀번호 설정</h1>
      </div>

      {isSlow && (
        <p className={styles.wake} role="status">
          <span aria-hidden="true">☕</span>
          <span>서버를 깨우는 중이에요</span>
        </p>
      )}

      {error !== null && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}

      {isDone ? (
        <>
          <p className={styles.wake} role="status">
            <span aria-hidden="true">✅</span>
            <span>
              비밀번호가 바뀌었어요
              <small>다른 기기에 남아 있던 로그인도 함께 해제됐어요.</small>
            </span>
          </p>
          <button className={styles.cta} type="button" onClick={() => navigate('/login')}>
            로그인하러 가기
          </button>
        </>
      ) : (
        <form onSubmit={handleSubmit} noValidate>
          <div className={styles.field}>
            <label htmlFor="new-password">새 비밀번호</label>
            <input
              id="new-password"
              type="password"
              autoComplete="new-password"
              placeholder={`${MIN_PASSWORD_LENGTH}자 이상`}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          <div className={styles.field}>
            <label htmlFor="new-password-confirm">새 비밀번호 확인</label>
            <input
              id="new-password-confirm"
              type="password"
              autoComplete="new-password"
              placeholder="한 번 더 입력하세요"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
            />
          </div>
          <button className={styles.cta} type="submit" disabled={isPending}>
            {isPending ? '변경 중…' : '비밀번호 변경'}
          </button>
        </form>
      )}
    </main>
  )
}
