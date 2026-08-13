import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { MIN_PASSWORD_LENGTH } from '../api/auth'
import { ApiError, TimeoutError } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { useSlowRequestHint } from '../hooks/useSlowRequestHint'
import styles from './AuthPage.module.css'

type Mode = 'login' | 'signup'

const COPY = {
  login: {
    submit: '로그인',
    pending: '로그인 중…',
    footQuestion: '아직 계정이 없으신가요?',
    footLink: '회원가입',
    footTo: '/signup',
  },
  signup: {
    submit: '회원가입',
    pending: '가입 중…',
    footQuestion: '이미 계정이 있으신가요?',
    footLink: '로그인',
    footTo: '/login',
  },
} as const

export default function AuthPage({ mode }: { mode: Mode }) {
  const copy = COPY[mode]
  const navigate = useNavigate()
  const auth = useAuth()

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isPending, setIsPending] = useState(false)
  const isSlow = useSlowRequestHint(isPending)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (isPending) return

    setError(null)

    // 백엔드도 같은 길이를 검사하지만, 여기서 먼저 걸러야 콜드스타트 30초를 기다린 끝에
    // "비밀번호가 짧습니다"를 보는 일이 없다.
    if (password.length < MIN_PASSWORD_LENGTH) {
      setError(`비밀번호는 ${MIN_PASSWORD_LENGTH}자 이상이어야 합니다.`)
      return
    }

    setIsPending(true)
    try {
      if (mode === 'login') {
        await auth.login(username.trim(), password)
      } else {
        await auth.signup(username.trim(), password)
      }
      navigate('/', { replace: true })
    } catch (caught) {
      if (caught instanceof ApiError || caught instanceof TimeoutError) {
        setError(caught.message)
      } else {
        setError('연결에 실패했습니다. 잠시 후 다시 시도해주세요.')
      }
    } finally {
      setIsPending(false)
    }
  }

  return (
    <main className={styles.page}>
      <div className={styles.brand}>
        <div className={styles.logo} aria-hidden="true">
          🍚
        </div>
        <h1>냉장고 한끼</h1>
        <p className={styles.tagline}>냉장고에 있는 재료로 한 끼</p>
      </div>

      {isSlow && (
        <p className={styles.wake} role="status">
          <span aria-hidden="true">☕</span>
          <span>
            서버를 깨우는 중이에요
            <small>무료 서버라 첫 요청은 30초쯤 걸려요. 조금만 기다려주세요.</small>
          </span>
        </p>
      )}

      {/* role="alert"라 오류가 생기면 화면 낭독기가 바로 읽는다. */}
      {error !== null && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}

      <form onSubmit={handleSubmit} noValidate>
        <div className={styles.field}>
          <label htmlFor="username">아이디</label>
          <input
            id="username"
            name="username"
            autoComplete="username"
            placeholder="아이디를 입력하세요"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
          />
        </div>

        <div className={styles.field}>
          <label htmlFor="password">비밀번호</label>
          <input
            id="password"
            name="password"
            type="password"
            autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
            placeholder={`${MIN_PASSWORD_LENGTH}자 이상`}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            aria-describedby="password-hint"
            required
          />
          <span className={styles.hint} id="password-hint">
            {MIN_PASSWORD_LENGTH}자 이상 입력해주세요
          </span>
        </div>

        <button className={styles.cta} type="submit" disabled={isPending}>
          {isPending ? copy.pending : copy.submit}
        </button>
      </form>

      <p className={styles.foot}>
        {copy.footQuestion} <Link to={copy.footTo}>{copy.footLink}</Link>
      </p>

      <div className={styles.bottom}>
        {/* 가입 없이 추천을 체험할 수 있다. 지인 5명에게 링크를 보낼 때 진입 문턱을 낮춘다. */}
        <Link className={styles.ghost} to="/">
          로그인 없이 둘러보기
        </Link>
      </div>
    </main>
  )
}
