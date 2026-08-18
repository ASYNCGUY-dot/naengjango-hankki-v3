import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { ApiError, TimeoutError } from '../api/client'
import {
  COOKING_LEVELS,
  COOKING_TOOLS,
  HEALTH_GOALS,
  HOUSEHOLD_SIZES,
  NOVELTY_PREFS,
  PURPOSES,
  getProfile,
  joinSelections,
  listAllergyOptions,
  splitSelections,
  updateProfile,
  type AllergyOption,
  type ProfileBody,
} from '../api/profile'
import { useAuth } from '../auth/context'
import { useSlowRequestHint } from '../hooks/useSlowRequestHint'
import styles from './OnboardingPage.module.css'

function describe(caught: unknown): string {
  if (caught instanceof ApiError || caught instanceof TimeoutError) return caught.message
  return '저장하지 못했어요. 잠시 후 다시 시도해주세요.'
}

/**
 * 식단 정보 입력(온보딩).
 *
 * 이 화면이 없어서 users.allergy가 계속 NULL이었고, 알레르기 제외가 아예 돌지 않았다.
 * 알레르기가 있는 사람에게는 위험한 구멍이라 이 화면의 핵심은 알레르기다.
 *
 * 알레르기는 자유 입력을 받지 않는다. 기존 데이터에 "콩"(태그는 "대두"), "@$#$" 같은
 * 값이 남아 있는데, 그렇게 저장되면 사용자는 골랐다고 믿지만 필터는 아무것도 안 거른다.
 * 서버가 실제 태그에서 만들어 준 목록에서만 고르게 한다.
 *
 * 성별·연령대는 가입에서 이미 받았다. 다시 묻지 않고, 저장할 때 기존 값을 그대로 실어
 * 보낸다 - PUT이 프로필 전체를 덮어쓰기 때문이다.
 */
export default function OnboardingPage() {
  const { userId, isAuthenticated } = useAuth()
  const navigate = useNavigate()

  const [allergyOptions, setAllergyOptions] = useState<AllergyOption[]>([])
  const [allergies, setAllergies] = useState<string[]>([])
  const [tools, setTools] = useState<string[]>([])
  const [healthGoal, setHealthGoal] = useState('')
  const [purpose, setPurpose] = useState('')
  const [cookingLevel, setCookingLevel] = useState('')
  const [noveltyPref, setNoveltyPref] = useState('')
  const [householdSize, setHouseholdSize] = useState(1)
  const [supplements, setSupplements] = useState('')
  const [medicalConditions, setMedicalConditions] = useState('')

  // 가입에서 받은 값. 화면에 다시 묻지 않지만 저장할 때 함께 보내야 한다.
  const [gender, setGender] = useState('')
  const [ageGroup, setAgeGroup] = useState('')

  // 알레르기·병력은 건강에 관한 정보라 가입 때의 포괄 동의로 덮지 않는다. 무엇에
  // 동의하는지 눈앞에 있을 때 여기서 따로 받는다. 서버도 같은 규칙을 강제한다 -
  // 동의 없이 건강 정보를 보내면 422로 거절한다(api/routers/profile.py).
  const [healthConsent, setHealthConsent] = useState(false)

  // 프로필을 못 읽었으면 저장을 막는다. PUT이 전체를 덮어쓰기 때문에, 성별·연령대를
  // 모르는 채로 보내면 가입 때 받은 값이 빈 문자열로 날아간다.
  const [isProfileLoaded, setIsProfileLoaded] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const isSlow = useSlowRequestHint(isSaving)

  useEffect(() => {
    if (userId === null) return
    const controller = new AbortController()

    listAllergyOptions(controller.signal)
      .then(setAllergyOptions)
      .catch(() => {
        // 목록을 못 받으면 고를 수가 없다. 조용히 넘기지 않고 알린다.
        if (!controller.signal.aborted) {
          setError('알레르기 목록을 불러오지 못했어요. 새로고침해주세요.')
        }
      })

    getProfile(userId, controller.signal)
      .then((profile) => {
        setGender(profile.gender ?? '')
        setAgeGroup(profile.age_group ?? '')
        // 이미 입력한 적이 있으면 그 값을 채워둔다 - 다시 처음부터 고르게 하지 않는다.
        setAllergies(splitSelections(profile.allergy))
        setTools(splitSelections(profile.cooking_tools))
        setHealthGoal(profile.health_goal ?? '')
        setPurpose(profile.purpose ?? '')
        setCookingLevel(profile.cooking_level ?? '')
        setNoveltyPref(profile.novelty_pref ?? '')
        setHouseholdSize(profile.household_size ?? 1)
        setSupplements(profile.supplements ?? '')
        setMedicalConditions(profile.medical_conditions ?? '')
        // 이미 동의한 사람에게 빈 체크박스를 보여주면 "동의한 적 없다"는 인상을 준다.
        setHealthConsent(profile.health_data_consent)
        setIsProfileLoaded(true)
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setError('내 정보를 불러오지 못했어요. 새로고침해주세요.')
        }
      })

    return () => controller.abort()
  }, [userId])

  function toggle(list: string[], value: string): string[] {
    return list.includes(value) ? list.filter((item) => item !== value) : [...list, value]
  }

  // 건강 정보를 실제로 넣은 사람에게만 동의를 묻는다. 수집하지 않는 것에 동의를
  // 요구하면 동의가 형식이 된다.
  const hasHealthData = allergies.length > 0 || medicalConditions.trim() !== ''

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (userId === null || isSaving) return

    setError(null)
    if (!healthGoal || !purpose || !cookingLevel || !noveltyPref) {
      setError('건강목표, 이용목적, 요리수준, 메뉴취향을 모두 골라주세요.')
      return
    }
    // 서버도 막지만 여기서 먼저 잡는다. 콜드스타트 30초를 기다린 끝에 "동의가
    // 필요합니다"를 보는 일이 없어야 한다.
    if (hasHealthData && !healthConsent) {
      setError('알레르기·병력 정보를 저장하려면 건강 정보 수집에 동의해주세요.')
      return
    }

    setIsSaving(true)
    try {
      const body: ProfileBody = {
        gender,
        age_group: ageGroup,
        allergy: joinSelections(allergies),
        health_goal: healthGoal,
        purpose,
        cooking_level: cookingLevel,
        supplements: supplements.trim() || '없음',
        household_size: householdSize,
        novelty_pref: noveltyPref,
        cooking_tools: joinSelections(tools),
        medical_conditions: medicalConditions.trim(),
        // 건강 정보를 안 넣었으면 동의도 보내지 않는다. 서버는 거절도 이력으로
        // 남기므로, 안 물어본 것을 동의로 기록하지 않게 하려면 값이 정확해야 한다.
        health_data_consent: hasHealthData && healthConsent,
      }
      await updateProfile(userId, body)
      navigate('/my', { replace: true })
    } catch (caught) {
      setError(describe(caught))
    } finally {
      setIsSaving(false)
    }
  }

  if (!isAuthenticated) {
    return (
      <div className={styles.guest}>
        <h1>식단 정보</h1>
        <p>로그인하면 알레르기와 건강목표를 추천에 반영할 수 있어요.</p>
        <Link to="/login">로그인하러 가기</Link>
      </div>
    )
  }

  // 프로필이 도착하기 전에는 폼을 내주지 않는다. 내주면 두 가지가 깨진다. 먼저 고른 칩이
  // 프로필 도착 시 초기값으로 덮여 사라지고(브라우저 확인 중에 실제로 그랬다), 성별·
  // 연령대를 모르는 채 저장하면 PUT이 프로필 전체를 덮어써 가입 때 받은 값이 날아간다.
  if (!isProfileLoaded) {
    return (
      <div className={styles.page}>
        <h1>식단 정보</h1>
        {error !== null ? (
          <p className={styles.error} role="alert">
            {error}
          </p>
        ) : (
          <p className={styles.notice} role="status">
            불러오는 중이에요…
          </p>
        )}
      </div>
    )
  }

  return (
    <div className={styles.page}>
      <h1>식단 정보</h1>
      <p className={styles.lead}>
        입력해두면 알레르기 재료가 든 레시피를 추천에서 빼드리고, 건강목표에 맞게 순서를 잡아요.
      </p>

      {error !== null && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}

      {isSlow && (
        <p className={styles.notice} role="status">
          저장하는 중이에요. 무료 서버라 조금 걸릴 수 있어요.
        </p>
      )}

      <form onSubmit={handleSubmit} noValidate>
        <fieldset className={`${styles.section} ${styles.safety}`}>
          <legend>알레르기</legend>
          <span className={styles.hint}>
            고른 재료가 든 레시피는 추천에서 제외돼요. 해당 없으면 비워두세요.
          </span>
          <ul className={styles.chips}>
            {allergyOptions.map((option) => {
              const selected = allergies.includes(option.value)
              return (
                <li key={option.value}>
                  <button
                    type="button"
                    className={selected ? `${styles.chip} ${styles.chipSelected}` : styles.chip}
                    aria-pressed={selected}
                    onClick={() => setAllergies((prev) => toggle(prev, option.value))}
                  >
                    {option.label}
                  </button>
                </li>
              )
            })}
          </ul>
        </fieldset>

        <fieldset className={styles.section}>
          <legend>조리 도구</legend>
          <span className={styles.hint}>가진 도구로 만들 수 있는 메뉴를 우선해요.</span>
          <ul className={styles.chips}>
            {COOKING_TOOLS.map((tool) => {
              const selected = tools.includes(tool)
              return (
                <li key={tool}>
                  <button
                    type="button"
                    className={selected ? `${styles.chip} ${styles.chipSelected}` : styles.chip}
                    aria-pressed={selected}
                    onClick={() => setTools((prev) => toggle(prev, tool))}
                  >
                    {tool}
                  </button>
                </li>
              )
            })}
          </ul>
        </fieldset>

        <Select id="health_goal" label="건강목표" value={healthGoal} onChange={setHealthGoal}
          options={HEALTH_GOALS} />
        <Select id="purpose" label="이용목적" value={purpose} onChange={setPurpose}
          options={PURPOSES} />
        <Select id="cooking_level" label="요리수준" value={cookingLevel} onChange={setCookingLevel}
          options={COOKING_LEVELS} />
        <Select id="novelty_pref" label="메뉴취향" value={noveltyPref} onChange={setNoveltyPref}
          options={NOVELTY_PREFS} />

        <div className={styles.field}>
          <label htmlFor="household_size">가구원 수</label>
          <select
            id="household_size"
            value={householdSize}
            onChange={(e) => setHouseholdSize(Number(e.target.value))}
          >
            {HOUSEHOLD_SIZES.map((size) => (
              <option key={size} value={size}>
                {size}인
              </option>
            ))}
          </select>
          <span className={styles.hint}>재료 수량을 이 인원에 맞춰 환산해요.</span>
        </div>

        <div className={styles.field}>
          <label htmlFor="supplements">복용 중인 영양제</label>
          <input
            id="supplements"
            type="text"
            placeholder="없으면 비워두세요"
            value={supplements}
            onChange={(e) => setSupplements(e.target.value)}
          />
        </div>

        <div className={styles.field}>
          <label htmlFor="medical_conditions">병력 정보</label>
          <input
            id="medical_conditions"
            type="text"
            placeholder="예: 고혈압, 당뇨 (선택)"
            value={medicalConditions}
            onChange={(e) => setMedicalConditions(e.target.value)}
          />
          <span className={styles.hint}>영양 안내에만 쓰이고 추천 목록에는 드러나지 않아요.</span>
        </div>

        {/* 건강 정보를 넣은 사람에게만 나타난다. 안 넣으면 수집하지 않으므로 물을 이유가
            없고, 물으면 동의가 형식이 된다. */}
        {hasHealthData && (
          <div className={styles.consent}>
            <label className={styles.consentLabel} htmlFor="health-consent">
              <input
                id="health-consent"
                type="checkbox"
                checked={healthConsent}
                onChange={(e) => setHealthConsent(e.target.checked)}
              />
              (필수) 알레르기·병력 정보 수집에 동의합니다
            </label>
            <p className={styles.hint}>
              건강에 관한 정보라 따로 여쭤봅니다. 알레르기 재료를 추천에서 빼는 것 외의
              용도로 쓰지 않아요. 동의하지 않으셔도 나머지 항목은 저장할 수 있어요.{' '}
              <Link to="/privacy" target="_blank" rel="noreferrer">
                자세히 보기
              </Link>
            </p>
          </div>
        )}

        <button className={styles.cta} type="submit" disabled={isSaving}>
          {isSaving ? '저장 중…' : '저장하기'}
        </button>
      </form>
    </div>
  )
}

function Select({
  id,
  label,
  value,
  onChange,
  options,
}: {
  id: string
  label: string
  value: string
  onChange: (value: string) => void
  options: readonly string[]
}) {
  return (
    <div className={styles.field}>
      <label htmlFor={id}>{label}</label>
      <select id={id} value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">선택하세요</option>
        {options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </div>
  )
}
