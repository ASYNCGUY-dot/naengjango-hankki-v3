import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'

import { MIN_PASSWORD_LENGTH, confirmPasswordReset } from '../api/auth'
import { ApiError, TimeoutError } from '../api/client'
import { useSlowRequestHint } from '../hooks/useSlowRequestHint'
import styles from './AuthPage.module.css'

function describe(caught: unknown): string {
  if (caught instanceof ApiError || caught instanceof TimeoutError) return caught.message
  return '연결에 실패했습니다. 잠시 후 다시 시도해주세요.'
}

/**
 * 초기화 안내 화면.
 *
 * "비밀번호 찾기"가 아니다. 비밀번호는 단방향 해시로 저장돼 서버도 알 수 없으므로
 * 알려줄 방법이 없다. 새로 설정할 수 있는 링크를 주는 것만 가능하다.
 *
 * 지금은 그 링크를 메일로 보내지 못한다(2026-08-18). Render 무료 웹 서비스가 SMTP
 * 포트(25/465/587) 아웃바운드를 막아서, 발송이 20초 시간 초과로 죽는다. 자격증명
 * 문제가 아니다 - 같은 코드가 로컬에서는 2.5초에 성공한다.
 *
 * 그래서 입력 폼을 뺐다. 폼을 남겨두면 "가입된 이메일이라면 링크를 보냈어요"라고
 * 말해놓고 아무것도 보내지 않는 화면이 된다. 사용자는 오지 않을 메일을 계속 기다린다.
 * 못 하는 일은 못 한다고 말하는 편이 낫다.
 *
 * 서버 쪽 엔드포인트와 /reset-password 화면은 그대로 살려뒀다. 만든 사람이
 * scripts/make_reset_link.py로 링크를 직접 만들어 전달하면 초기화는 지금도 된다.
 * 메일 경로가 열리면(유료 인스턴스 또는 HTTPS 메일 API) 이 화면만 되돌리면 된다.
 */
export function ForgotPasswordPage() {
  return (
    <main className={styles.page}>
      <div className={styles.brand}>
        <h1>비밀번호 초기화</h1>
        <p className={styles.tagline}>지금은 만든 사람에게 연락해주세요</p>
      </div>

      <p className={styles.wake} role="status">
        <span aria-hidden="true">💬</span>
        <span>
          아직 초기화 메일을 보내드릴 수 없어요
          <small>
            만든 사람에게 알려주시면 초기화 링크를 직접 만들어 보내드려요. 링크를 받으시면 30분
            안에 새 비밀번호를 설정하시면 됩니다.
          </small>
        </span>
      </p>

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
