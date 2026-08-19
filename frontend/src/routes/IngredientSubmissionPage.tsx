import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { ApiError, TimeoutError } from '../api/client'
import {
  getMySubmission,
  listMySubmissions,
  submitIngredient,
  updateSubmission,
  type MySubmissionItem,
} from '../api/ingredientSubmissions'
import { useAuth } from '../auth/context'
import styles from './MyRecipesPage.module.css'

const EMPTY_FORM = {
  ingredient_name: '',
  calorie: '',
  carbs_g: '',
  protein_g: '',
  fat_g: '',
  sodium_mg: '',
  price_per_100g: '',
}

type FormState = typeof EMPTY_FORM

/** 100g당 값이라는 것을 라벨에 박아둔다. 단위를 오해하면 값 자체가 무의미해진다. */
const FIELDS: { key: keyof Omit<FormState, 'ingredient_name'>; label: string }[] = [
  { key: 'calorie', label: '열량 (kcal / 100g)' },
  { key: 'carbs_g', label: '탄수화물 (g / 100g)' },
  { key: 'protein_g', label: '단백질 (g / 100g)' },
  { key: 'fat_g', label: '지방 (g / 100g)' },
  { key: 'sodium_mg', label: '나트륨 (mg / 100g)' },
  { key: 'price_per_100g', label: '가격 (원 / 100g)' },
]

function describe(caught: unknown): string {
  if (caught instanceof ApiError || caught instanceof TimeoutError) return caught.message
  return '요청에 실패했어요. 잠시 후 다시 시도해주세요.'
}

/** 빈 칸은 0이 아니라 "모름"이다. 0으로 보내면 열량 0kcal인 재료가 된다. */
function toNumber(value: string): number | null {
  return value.trim() === '' ? null : Number(value)
}

/**
 * 재료 정보 등록 - 식품영양성분 DB(30만 건)에 없는 재료를 사용자가 채워 넣는 화면.
 *
 * 서버에는 V2 때부터 있었는데 V3 화면이 부르지 않아 아무도 쓸 수 없었다(2026-08-19까지).
 *
 * 공식 DB에 이미 있는 이름이거나 남이 먼저 등록한 이름이면 승인 대기로 들어간다.
 * 공식 값을 사용자 입력이 조용히 덮으면 다른 사람의 영양 계산까지 같이 바뀌기 때문이다.
 */
export default function IngredientSubmissionPage() {
  const { userId, isAuthenticated } = useAuth()

  const [submissions, setSubmissions] = useState<MySubmissionItem[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const [editing, setEditing] = useState<number | 'new' | null>(null)
  const [form, setForm] = useState<FormState>(EMPTY_FORM)
  const [isSaving, setIsSaving] = useState(false)

  useEffect(() => {
    if (userId === null) return
    const controller = new AbortController()
    listMySubmissions(userId, controller.signal)
      .then(setSubmissions)
      .catch((caught: unknown) => {
        if (!controller.signal.aborted) setError(describe(caught))
      })
      .finally(() => {
        if (!controller.signal.aborted) setIsLoading(false)
      })
    return () => controller.abort()
  }, [userId])

  if (!isAuthenticated) {
    return (
      <div className={styles.guest}>
        <h1>재료 정보 등록</h1>
        <p>재료 정보를 등록하려면 로그인이 필요해요.</p>
        <Link className={styles.primary} to="/login">
          로그인하러 가기
        </Link>
      </div>
    )
  }

  async function startEdit(submissionId: number) {
    if (userId === null) return
    setError(null)
    setNotice(null)
    try {
      const detail = await getMySubmission(submissionId, userId)
      setForm({
        ingredient_name: detail.ingredient_name,
        calorie: detail.calorie === null ? '' : String(detail.calorie),
        carbs_g: detail.carbs_g === null ? '' : String(detail.carbs_g),
        protein_g: detail.protein_g === null ? '' : String(detail.protein_g),
        fat_g: detail.fat_g === null ? '' : String(detail.fat_g),
        sodium_mg: detail.sodium_mg === null ? '' : String(detail.sodium_mg),
        price_per_100g: detail.price_per_100g === null ? '' : String(detail.price_per_100g),
      })
      setEditing(submissionId)
    } catch (caught) {
      setError(describe(caught))
    }
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    if (userId === null || editing === null) return
    setIsSaving(true)
    setError(null)
    setNotice(null)
    const body = {
      ingredient_name: form.ingredient_name.trim(),
      calorie: toNumber(form.calorie),
      carbs_g: toNumber(form.carbs_g),
      protein_g: toNumber(form.protein_g),
      fat_g: toNumber(form.fat_g),
      sodium_mg: toNumber(form.sodium_mg),
      price_per_100g: toNumber(form.price_per_100g),
    }
    try {
      const res =
        editing === 'new'
          ? await submitIngredient(userId, body)
          : await updateSubmission(editing, userId, body)
      setNotice(
        res.status === 'pending'
          ? '이미 등록된 이름이라 승인을 기다립니다. 공식 자료가 있는 재료는 그 값을 먼저 써요.'
          : '등록했어요. 알려주셔서 고맙습니다.',
      )
      setEditing(null)
      setForm(EMPTY_FORM)
      setSubmissions(await listMySubmissions(userId))
    } catch (caught) {
      setError(describe(caught))
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <div className={styles.page}>
      <h1>재료 정보 등록</h1>

      <p className={styles.notice}>
        공식 식품영양성분 DB에 없는 재료의 영양 정보를 알려주세요. 이미 있는 재료는 공식
        자료를 먼저 쓰기 때문에 승인 대기로 들어가요.
      </p>

      {error !== null && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}
      {notice !== null && (
        <p className={styles.notice} role="status">
          {notice}
        </p>
      )}

      {editing === null ? (
        <button
          className={styles.primary}
          type="button"
          onClick={() => {
            setForm(EMPTY_FORM)
            setEditing('new')
          }}
        >
          새 재료 등록
        </button>
      ) : (
        <form className={styles.form} onSubmit={(event) => void handleSubmit(event)}>
          <label htmlFor="ingredient-name">재료 이름</label>
          <input
            id="ingredient-name"
            value={form.ingredient_name}
            required
            maxLength={40}
            onChange={(e) => setForm({ ...form, ingredient_name: e.target.value })}
          />

          {FIELDS.map((field) => (
            <div key={field.key} className={styles.formRow}>
              <label htmlFor={`ingredient-${field.key}`}>{field.label}</label>
              <input
                id={`ingredient-${field.key}`}
                type="number"
                min="0"
                step="0.1"
                value={form[field.key]}
                onChange={(e) => setForm({ ...form, [field.key]: e.target.value })}
              />
            </div>
          ))}

          <div className={styles.formActions}>
            <button className={styles.primary} type="submit" disabled={isSaving}>
              {isSaving ? '저장 중…' : editing === 'new' ? '등록하기' : '수정하기'}
            </button>
            <button className={styles.ghost} type="button" onClick={() => setEditing(null)}>
              취소
            </button>
          </div>
        </form>
      )}

      {isLoading ? (
        <p className={styles.empty}>불러오는 중…</p>
      ) : submissions.length === 0 ? (
        <p className={styles.empty}>아직 등록한 재료가 없어요.</p>
      ) : (
        <ul className={styles.list}>
          {submissions.map((item) => (
            <li key={item.id}>
              <div className={styles.itemHead}>
                <span className={styles.itemName}>{item.ingredient_name}</span>
                <span
                  className={
                    item.status === 'approved'
                      ? `${styles.status} ${styles.approved}`
                      : styles.status
                  }
                >
                  {item.status === 'approved' ? '반영됨' : '승인 대기'}
                </span>
              </div>
              <p className={styles.itemMeta}>
                {item.calorie === null ? '열량 미입력' : `${item.calorie} kcal / 100g`}
              </p>
              <div className={styles.itemActions}>
                <button
                  className={styles.ghost}
                  type="button"
                  onClick={() => void startEdit(item.id)}
                >
                  수정
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
