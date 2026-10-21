import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { MIN_PASSWORD_LENGTH, sessionStore, type SignupBody } from '../api/auth'
import { getProfile, getProfileOptions, type ProfileOptions } from '../api/profile'
import { ApiError, TimeoutError } from '../api/client'
import { useAuth } from '../auth/context'
import { useSlowRequestHint } from '../hooks/useSlowRequestHint'
import { useDeferredFocus } from '../hooks/비동기초점'
import Icon from '../components/아이콘'
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

/**
 * 로그인 직후 온보딩으로 보낼지 정한다.
 *
 * 프로필 조회가 실패하면 보내지 않는다. 확실하지 않은데 보내면, 이미 다 입력해둔
 * 사람이 로그인할 때마다 같은 화면을 다시 보게 된다.
 */
async function needsOnboarding(): Promise<boolean> {
  const userId = sessionStore.getUserId()
  if (userId === null) return false
  try {
    return (await getProfile(userId)).has_profile === false
  } catch {
    return false
  }
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
  const [errorField, setErrorField] = useState<string | null>(null)
  const formRef = useRef<HTMLFormElement>(null)
  const errorRef = useRef<HTMLParagraphElement>(null)
  const optionsFocus = useRef<(() => boolean) | null>(null)
  const submitFocus = useRef<(() => boolean) | null>(null)
  const { capture: captureFocus } = useDeferredFocus()
  const [isPending, setIsPending] = useState(false)
  const isSlow = useSlowRequestHint(isPending)

  // 선택지는 서버가 정한다. 화면이 목록을 들고 있다가 서버가 아는 값과 어긋난 적이 있다.
  const [options, setOptions] = useState<ProfileOptions | null>(null)
  const [optionsState, setOptionsState] = useState<'loading' | 'loaded' | 'error'>('loading')
  const [optionsAttempt, setOptionsAttempt] = useState(0)
  useEffect(() => {
    if (mode !== 'signup') return
    const controller = new AbortController()
    getProfileOptions(controller.signal)
      .then((result) => {
        if (controller.signal.aborted) return
        if (!result.genders.length || !result.age_groups.length) {
          setOptionsState('error')
          return
        }
        setOptions(result)
        setOptionsState('loaded')
      })
      .catch(() => {
        if (!controller.signal.aborted) setOptionsState('error')
      })
    return () => controller.abort()
  }, [mode, optionsAttempt])

  useEffect(() => {
    if (error && errorField === null) {
      const canRestore = submitFocus.current
      submitFocus.current = null
      if (canRestore?.()) errorRef.current?.focus()
    }
  }, [error, errorField])

  useEffect(() => {
    if (mode === 'signup' && optionsState === 'loaded') {
      const canRestore = optionsFocus.current
      optionsFocus.current = null
      if (canRestore?.()) formRef.current?.querySelector<HTMLSelectElement>('#gender')?.focus()
    }
  }, [mode, optionsState])

  const set = (key: keyof typeof EMPTY_SIGNUP) => (value: string) =>
    setForm((prev) => ({ ...prev, [key]: value }))

  function validate(): { field: string; message: string } | null {
    // 백엔드도 같은 것들을 검사하지만, 여기서 먼저 걸러야 콜드스타트 30초를 기다린 끝에
    // "비밀번호가 짧습니다"를 보는 일이 없다.
    if (!form.username.trim()) return { field: 'username', message: '아이디를 입력해주세요.' }
    if (form.password.length < MIN_PASSWORD_LENGTH) {
      return { field: 'password', message: `비밀번호는 ${MIN_PASSWORD_LENGTH}자 이상이어야 합니다.` }
    }
    if (mode === 'login') return null

    if (!form.name.trim()) return { field: 'name', message: '이름을 입력해주세요.' }
    if (!form.phone.trim()) return { field: 'phone', message: '연락처를 입력해주세요.' }
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(form.email.trim())) {
      return { field: 'email', message: '이메일 형식이 올바르지 않습니다.' }
    }
    if (!form.gender) return { field: 'gender', message: '성별을 선택해주세요.' }
    if (!form.age_group) return { field: 'age_group', message: '연령대를 선택해주세요.' }
    if (!agreedTerms || !agreedPrivacy) {
      return {
        field: !agreedTerms ? 'agree-terms' : 'agree-privacy',
        message: '이용약관과 개인정보 수집·이용에 동의해야 가입할 수 있습니다.',
      }
    }
    return null
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (isPending || (mode === 'signup' && optionsState !== 'loaded')) return

    setError(null)
    setErrorField(null)
    const problem = validate()
    if (problem !== null) {
      setError(problem.message)
      setErrorField(problem.field)
      formRef.current?.querySelector<HTMLElement>(`#${problem.field}`)?.focus()
      return
    }

    submitFocus.current = captureFocus()
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
      // 식단 정보를 아직 안 넣은 사람은 온보딩으로 보낸다. 알레르기가 없으면 필터가
      // 아예 돌지 않으므로, 처음 들어온 사람에게 이 화면을 안 보여주면 그 사실을
      // 알 방법이 없다. 건너뛸 수는 있게 해뒀다(OnboardingPage).
      navigate(await needsOnboarding() ? '/onboarding' : '/', { replace: true })
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
    <main className={`${styles.page} ${mode === 'signup' ? styles.signup : ''}`}>
      <header className={styles.brand}>
        <Icon name="bowl" size={26} className={styles.logo} />
        <h1>냉장고 한끼</h1>
      </header>

      {mode === 'login' ? (
        <section className={styles.intro} aria-label="냉장고 한끼 소개">
          <p className={styles.tagline}>냉장고 속 재료로,<br />오늘 한 끼.</p>
          <p className={styles.description}>내 재료로 요리를 찾고, 집밥을 나눠요.</p>
          <div className={styles.photos} aria-hidden="true">
            <div className={styles.ricePhoto} />
            <div className={styles.stewPhoto} />
          </div>
        </section>
      ) : (
        <div className={styles.signupIntro}>
          <h2>우리 집 식탁을 시작해요</h2>
          <p className={styles.description}>나에게 맞는 한 끼를 함께 찾아봐요.</p>
        </div>
      )}

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
        <p id="auth-error" ref={errorRef} className={styles.error} role="alert" tabIndex={-1}>
          {error}
        </p>
      )}

      <form ref={formRef} className={styles.form} onSubmit={handleSubmit} noValidate>
        <Field id="username" label="아이디" value={form.username} onChange={set('username')}
          invalid={errorField === 'username'}
          autoComplete="username" placeholder="아이디를 입력하세요" />

        <Field id="password" label="비밀번호" value={form.password} onChange={set('password')}
          invalid={errorField === 'password'}
          type="password"
          autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
          placeholder={mode === 'login' ? '비밀번호를 입력하세요' : `${MIN_PASSWORD_LENGTH}자 이상`}
          hint={mode === 'signup' ? `${MIN_PASSWORD_LENGTH}자 이상 입력해주세요` : undefined} />

        {mode === 'signup' && (
          <>
            <Field id="name" label="이름" value={form.name} onChange={set('name')}
              invalid={errorField === 'name'}
              autoComplete="name" placeholder="이름을 입력하세요" />

            <Field id="phone" label="연락처" value={form.phone} onChange={set('phone')}
              invalid={errorField === 'phone'}
              type="tel" autoComplete="tel" placeholder="010-0000-0000" />

            <Field id="email" label="이메일" value={form.email} onChange={set('email')}
              invalid={errorField === 'email'}
              type="email" autoComplete="email" placeholder="name@example.com"
              hint="비밀번호를 잊었을 때 초기화 링크를 받을 주소예요" />

            {optionsState === 'loading' && (
              <p id="profile-options-state" className={styles.hint} role="status">
                성별·연령대 선택지를 불러오는 중이에요…
              </p>
            )}
            {optionsState === 'error' && (
              <div className={styles.optionsNotice}>
                <p id="profile-options-state" role="alert">
                  성별·연령대 선택지를 불러오지 못했어요. 다시 불러온 뒤 가입할 수 있어요.
                </p>
                <button type="button" className={styles.retry} onClick={() => {
                  optionsFocus.current = captureFocus()
                  setOptionsState('loading')
                  setOptionsAttempt((attempt) => attempt + 1)
                }}>선택지 다시 불러오기</button>
              </div>
            )}

            <div className={styles.field}>
              <label htmlFor="gender">성별</label>
              <select id="gender" value={form.gender} onChange={(e) => set('gender')(e.target.value)}
                required disabled={optionsState !== 'loaded'} aria-invalid={errorField === 'gender'}
                aria-describedby={errorField === 'gender' ? 'auth-error' : optionsState !== 'loaded' ? 'profile-options-state' : undefined}>
                <option value="">선택하세요</option>
                {(options?.genders ?? []).map((option) => (
                  <option key={option} value={option}>{option}</option>
                ))}
              </select>
            </div>

            <div className={styles.field}>
              <label htmlFor="age_group">연령대</label>
              <select id="age_group" value={form.age_group}
                required disabled={optionsState !== 'loaded'} aria-invalid={errorField === 'age_group'}
                aria-describedby={errorField === 'age_group' ? 'auth-error' : optionsState !== 'loaded' ? 'profile-options-state' : undefined}
                onChange={(e) => set('age_group')(e.target.value)}>
                <option value="">선택하세요</option>
                {(options?.age_groups ?? []).map((option) => (
                  <option key={option} value={option}>{option}</option>
                ))}
              </select>
            </div>

            <fieldset className={styles.consents}>
              <legend>약관 동의</legend>
              {/* 라벨과 링크를 분리한다. 라벨 안에 링크를 넣으면 링크를 누를 때 체크박스가
                  함께 토글돼서, 문서를 보려던 사람이 동의를 켜버린다. */}
              <Checkbox id="agree-terms" checked={agreedTerms} onChange={setAgreedTerms}
                required invalid={errorField === 'agree-terms'}
                label="(필수) 이용약관에 동의합니다"
                to="/terms" linkLabel="이용약관 보기 (새 창)" />
              <Checkbox id="agree-privacy" checked={agreedPrivacy} onChange={setAgreedPrivacy}
                required invalid={errorField === 'agree-privacy'}
                label="(필수) 개인정보 수집·이용에 동의합니다"
                to="/privacy" linkLabel="개인정보 처리방침 보기 (새 창)" />
              <Checkbox id="agree-marketing" checked={agreedMarketing} onChange={setAgreedMarketing}
                label="(선택) 마케팅 정보 수신에 동의합니다" />
              <p className={styles.hint}>
                아이디·이름·연락처·이메일·성별·연령대를 받습니다. 가입 후 식단 정보를
                입력하시면 알레르기와 병력 정보도 저장되는데, 이건 넣지 않아도 서비스를 쓸 수
                있어요. 지우고 싶으시면 만든 사람에게 말씀해주세요.
              </p>
            </fieldset>
          </>
        )}

        <button className={styles.cta} type="submit"
          disabled={isPending || (mode === 'signup' && optionsState !== 'loaded')}>
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

      {/* "로그인 없이 둘러보기"가 여기 있었는데 뺐다(2026-08-20). 홈이 로그인 화면이
          되면서 그 링크가 자기 자신을 가리키게 됐다. 로그인 없이 열리는 것은 레시피
          상세 하나뿐이고, 그건 공유 링크로 들어오는 자리라 여기서 갈 곳이 아니다. */}
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
  invalid?: boolean
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
        required
        aria-invalid={props.invalid}
        aria-describedby={[hintId, props.invalid ? 'auth-error' : undefined].filter(Boolean).join(' ') || undefined}
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
  /** 있으면 라벨 옆에 "보기" 링크를 단다. 동의 대상 문서로 가는 길이다. */
  to?: string
  linkLabel?: string
  required?: boolean
  invalid?: boolean
}) {
  return (
    <div className={styles.checkboxRow}>
      <label className={styles.checkbox} htmlFor={props.id}>
        <input
          id={props.id}
          type="checkbox"
          checked={props.checked}
          required={props.required}
          aria-invalid={props.invalid}
          aria-describedby={props.invalid ? 'auth-error' : undefined}
          onChange={(e) => props.onChange(e.target.checked)}
        />
        {props.label}
      </label>
      {props.to !== undefined && (
        // 새 탭으로 연다. 같은 탭에서 열면 지금까지 입력한 가입 정보가 날아간다.
        <Link className={styles.consentLink} to={props.to} target="_blank" rel="noreferrer"
          aria-label={props.linkLabel ?? '보기 (새 창)'} title={props.linkLabel ?? '보기 (새 창)'}>
          보기
        </Link>
      )}
    </div>
  )
}
