import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import {
  AGE_GROUP_OPTIONS,
  GENDER_OPTIONS,
  MIN_PASSWORD_LENGTH,
  type SignupBody,
} from '../api/auth'
import { ApiError, TimeoutError } from '../api/client'
import { useAuth } from '../auth/context'
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

const EMPTY_SIGNUP = {
  username: '',
  password: '',
  name: '',
  phone: '',
  email: '',
  gender: '',
  age_group: '',
}

export default function AuthPage({ mode }: { mode: Mode }) {
  const copy = COPY[mode]
  const navigate = useNavigate()
  const auth = useAuth()

  const [form, setForm] = useState(EMPTY_SIGNUP)
  const [agreedTerms, setAgreedTerms] = useState(false)
  const [agreedPrivacy, setAgreedPrivacy] = useState(false)
  const [agreedMarketing, setAgreedMarketing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isPending, setIsPending] = useState(false)
  const isSlow = useSlowRequestHint(isPending)

  const set = (key: keyof typeof EMPTY_SIGNUP) => (value: string) =>
    setForm((prev) => ({ ...prev, [key]: value }))

  function validate(): string | null {
    // 백엔드도 같은 것들을 검사하지만, 여기서 먼저 걸러야 콜드스타트 30초를 기다린 끝에
    // "비밀번호가 짧습니다"를 보는 일이 없다.
    if (form.password.length < MIN_PASSWORD_LENGTH) {
      return `비밀번호는 ${MIN_PASSWORD_LENGTH}자 이상이어야 합니다.`
    }
    if (mode === 'login') return null

    if (!form.name.trim()) return '이름을 입력해주세요.'
    if (!form.phone.trim()) return '연락처를 입력해주세요.'
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(form.email.trim())) {
      return '이메일 형식이 올바르지 않습니다.'
    }
    if (!form.gender) return '성별을 선택해주세요.'
    if (!form.age_group) return '연령대를 선택해주세요.'
    if (!agreedTerms || !agreedPrivacy) {
      return '이용약관과 개인정보 수집·이용에 동의해야 가입할 수 있습니다.'
    }
    return null
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (isPending) return

    setError(null)
    const problem = validate()
    if (problem !== null) {
      setError(problem)
      return
    }

    setIsPending(true)
    try {
      if (mode === 'login') {
        await auth.login(form.username.trim(), form.password)
      } else {
        const body: SignupBody = {
          username: form.username.trim(),
          password: form.password,
          name: form.name.trim(),
          phone: form.phone.trim(),
          email: form.email.trim(),
          gender: form.gender,
          age_group: form.age_group,
          consents: {
            terms_of_service: agreedTerms,
            privacy: agreedPrivacy,
            marketing: agreedMarketing,
          },
        }
        await auth.signup(body)
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
        <Field id="username" label="아이디" value={form.username} onChange={set('username')}
          autoComplete="username" placeholder="아이디를 입력하세요" />

        <Field id="password" label="비밀번호" value={form.password} onChange={set('password')}
          type="password"
          autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
          placeholder={`${MIN_PASSWORD_LENGTH}자 이상`}
          hint={`${MIN_PASSWORD_LENGTH}자 이상 입력해주세요`} />

        {mode === 'signup' && (
          <>
            <Field id="name" label="이름" value={form.name} onChange={set('name')}
              autoComplete="name" placeholder="이름을 입력하세요" />

            <Field id="phone" label="연락처" value={form.phone} onChange={set('phone')}
              type="tel" autoComplete="tel" placeholder="010-0000-0000" />

            <Field id="email" label="이메일" value={form.email} onChange={set('email')}
              type="email" autoComplete="email" placeholder="name@example.com"
              hint="비밀번호를 잊었을 때 초기화 링크를 받을 주소예요" />

            <div className={styles.field}>
              <label htmlFor="gender">성별</label>
              <select id="gender" value={form.gender} onChange={(e) => set('gender')(e.target.value)}>
                <option value="">선택하세요</option>
                {GENDER_OPTIONS.map((option) => (
                  <option key={option} value={option}>{option}</option>
                ))}
              </select>
            </div>

            <div className={styles.field}>
              <label htmlFor="age_group">연령대</label>
              <select id="age_group" value={form.age_group}
                onChange={(e) => set('age_group')(e.target.value)}>
                <option value="">선택하세요</option>
                {AGE_GROUP_OPTIONS.map((option) => (
                  <option key={option} value={option}>{option}</option>
                ))}
              </select>
            </div>

            <fieldset className={styles.consents}>
              <legend>약관 동의</legend>
              <Checkbox id="agree-terms" checked={agreedTerms} onChange={setAgreedTerms}
                label="(필수) 이용약관에 동의합니다" />
              <Checkbox id="agree-privacy" checked={agreedPrivacy} onChange={setAgreedPrivacy}
                label="(필수) 개인정보 수집·이용에 동의합니다" />
              <Checkbox id="agree-marketing" checked={agreedMarketing} onChange={setAgreedMarketing}
                label="(선택) 마케팅 정보 수신에 동의합니다" />
              <p className={styles.hint}>
                수집 항목: 아이디, 이름, 연락처, 이메일, 성별, 연령대. 서비스 이용과 계정
                관리를 위해 쓰이며, 회원 탈퇴 시 지웁니다.
              </p>
            </fieldset>
          </>
        )}

        <button className={styles.cta} type="submit" disabled={isPending}>
          {isPending ? copy.pending : copy.submit}
        </button>
      </form>

      {mode === 'login' && (
        <p className={styles.foot}>
          <Link to="/forgot-password">비밀번호를 잊으셨나요?</Link>
        </p>
      )}

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

function Field(props: {
  id: string
  label: string
  value: string
  onChange: (value: string) => void
  type?: string
  autoComplete?: string
  placeholder?: string
  hint?: string
}) {
  const hintId = props.hint ? `${props.id}-hint` : undefined
  return (
    <div className={styles.field}>
      <label htmlFor={props.id}>{props.label}</label>
      <input
        id={props.id}
        name={props.id}
        type={props.type ?? 'text'}
        autoComplete={props.autoComplete}
        placeholder={props.placeholder}
        value={props.value}
        onChange={(e) => props.onChange(e.target.value)}
        aria-describedby={hintId}
      />
      {props.hint && (
        <span className={styles.hint} id={hintId}>
          {props.hint}
        </span>
      )}
    </div>
  )
}

function Checkbox(props: {
  id: string
  checked: boolean
  onChange: (checked: boolean) => void
  label: string
}) {
  return (
    <label className={styles.checkbox} htmlFor={props.id}>
      <input
        id={props.id}
        type="checkbox"
        checked={props.checked}
        onChange={(e) => props.onChange(e.target.checked)}
      />
      {props.label}
    </label>
  )
}
