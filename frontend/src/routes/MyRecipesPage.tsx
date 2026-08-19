import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { ApiError, TimeoutError } from '../api/client'
import {
  deleteMyRecipe,
  getMyRecipe,
  listMyRecipes,
  submitMyRecipe,
  updateMyRecipe,
  type MyRecipeItem,
} from '../api/myRecipes'
import { listCategories } from '../api/recipes'
import { useAuth } from '../auth/context'
import styles from './MyRecipesPage.module.css'

const EMPTY_FORM = {
  menu_name: '',
  category: '반찬',
  calorie: '',
  ingredients_text: '',
  steps_text: '',
}

function describe(caught: unknown): string {
  if (caught instanceof ApiError || caught instanceof TimeoutError) return caught.message
  return '요청에 실패했어요. 잠시 후 다시 시도해주세요.'
}

/**
 * 내 레시피 - 직접 만든 레시피를 올리고 상태를 확인하는 화면.
 *
 * 서버에는 V2 때부터 있었는데 V3 화면이 부르지 않아 아무도 쓸 수 없었다(2026-08-19까지).
 *
 * 상태와 추천 수를 함께 보여주는 것이 이 화면의 핵심이다. 등록하면 바로 공개되는 게
 * 아니라 관문이 둘 있다 - 이름이 기존 레시피와 겹치면 관리자 승인을 기다리고, 승인된
 * 뒤에도 추천이 일정 수 쌓여야 다른 사람의 추천 후보가 된다. 두 값을 안 보여주면
 * "왜 내 레시피가 아무 데도 안 나오지"에 답할 방법이 없다.
 */
export default function MyRecipesPage() {
  const { userId, isAuthenticated } = useAuth()

  const [recipes, setRecipes] = useState<MyRecipeItem[]>([])
  // 분류 목록은 서버가 준다. 화면이 따로 들고 있으면 서버가 아는 값과 조용히
  // 어긋난다 - V3_HANDOFF 8.-5에 같은 사고 네 건이 적혀 있다.
  const [categories, setCategories] = useState<string[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  // null이면 폼을 닫은 상태. 숫자면 그 레시피를 수정 중, 'new'면 새로 등록 중.
  const [editing, setEditing] = useState<number | 'new' | null>(null)
  const [form, setForm] = useState(EMPTY_FORM)
  const [isSaving, setIsSaving] = useState(false)

  useEffect(() => {
    if (userId === null) return
    const controller = new AbortController()
    listMyRecipes(userId, controller.signal)
      .then(setRecipes)
      .catch((caught: unknown) => {
        if (!controller.signal.aborted) setError(describe(caught))
      })
      .finally(() => {
        if (!controller.signal.aborted) setIsLoading(false)
      })
    listCategories(controller.signal)
      .then((rows) => setCategories(rows.map((row) => row.category)))
      // 못 받으면 지금 고른 값 하나만 남는다. 목록 자체는 등록을 막을 만큼
      // 중요하지 않아서 실패해도 화면을 세우지 않는다.
      .catch(() => {})
    return () => controller.abort()
  }, [userId])

  if (!isAuthenticated) {
    return (
      <div className={styles.guest}>
        <h1>내 레시피</h1>
        <p>직접 만든 레시피를 올리려면 로그인이 필요해요.</p>
        <Link className={styles.primary} to="/login">
          로그인하러 가기
        </Link>
      </div>
    )
  }

  async function refresh() {
    if (userId === null) return
    setRecipes(await listMyRecipes(userId))
  }

  async function startEdit(recipeId: number) {
    if (userId === null) return
    setError(null)
    setNotice(null)
    try {
      const detail = await getMyRecipe(recipeId, userId)
      setForm({
        menu_name: detail.menu_name,
        category: detail.category ?? '반찬',
        calorie: detail.calorie === null ? '' : String(detail.calorie),
        ingredients_text: detail.ingredients_text,
        steps_text: detail.steps_text,
      })
      setEditing(recipeId)
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
      menu_name: form.menu_name.trim(),
      category: form.category,
      // 빈 칸은 0이 아니라 "모름"이다. 0으로 보내면 열량 0kcal인 레시피가 된다.
      calorie: form.calorie.trim() === '' ? null : Number(form.calorie),
      ingredients_text: form.ingredients_text.trim(),
      steps_text: form.steps_text.trim(),
    }
    try {
      const res =
        editing === 'new'
          ? await submitMyRecipe(userId, body)
          : await updateMyRecipe(editing, userId, body)
      setNotice(
        res.status === 'pending'
          ? '같은 이름의 레시피가 이미 있어서 승인을 기다립니다. 승인되면 다른 분들도 볼 수 있어요.'
          : '등록했어요. 추천이 쌓이면 다른 분들의 추천 목록에도 올라가요.',
      )
      setEditing(null)
      setForm(EMPTY_FORM)
      await refresh()
    } catch (caught) {
      setError(describe(caught))
    } finally {
      setIsSaving(false)
    }
  }

  async function handleDelete(recipeId: number) {
    if (userId === null) return
    setError(null)
    setNotice(null)
    try {
      await deleteMyRecipe(recipeId, userId)
      await refresh()
    } catch (caught) {
      setError(describe(caught))
    }
  }

  return (
    <div className={styles.page}>
      <h1>내 레시피</h1>

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
          새 레시피 등록
        </button>
      ) : (
        <form className={styles.form} onSubmit={(event) => void handleSubmit(event)}>
          <label htmlFor="recipe-name">메뉴 이름</label>
          <input
            id="recipe-name"
            value={form.menu_name}
            required
            maxLength={60}
            onChange={(e) => setForm({ ...form, menu_name: e.target.value })}
          />

          <label htmlFor="recipe-category">분류</label>
          <select
            id="recipe-category"
            value={form.category}
            onChange={(e) => setForm({ ...form, category: e.target.value })}
          >
            {(categories.length > 0 ? categories : [form.category]).map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>

          <label htmlFor="recipe-calorie">열량 (kcal, 모르면 비워두세요)</label>
          <input
            id="recipe-calorie"
            type="number"
            min="0"
            value={form.calorie}
            onChange={(e) => setForm({ ...form, calorie: e.target.value })}
          />

          <label htmlFor="recipe-ingredients">재료 (한 줄에 하나씩)</label>
          {/* 여기 적은 이름에서 알레르기 태그를 뽑는다. 통칭으로 적어야 알레르기가 있는
              사람에게 이 레시피가 걸러진다 - 그래서 안내를 라벨이 아니라 눈에 띄게 둔다. */}
          <p className={styles.hint}>
            <strong>재료 이름은 통칭으로 적어주세요.</strong> 여기 적은 이름으로 알레르기를
            판단해요. 예: “계란 2개”, “우유 200ml”
          </p>
          <textarea
            id="recipe-ingredients"
            rows={5}
            value={form.ingredients_text}
            required
            placeholder={'돼지고기 100g\n김치 200g\n두부 100g'}
            onChange={(e) => setForm({ ...form, ingredients_text: e.target.value })}
          />

          <label htmlFor="recipe-steps">조리 순서 (한 줄에 한 단계)</label>
          <textarea
            id="recipe-steps"
            rows={5}
            value={form.steps_text}
            required
            placeholder={'재료를 먹기 좋게 썬다\n냄비에 넣고 끓인다'}
            onChange={(e) => setForm({ ...form, steps_text: e.target.value })}
          />

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
      ) : recipes.length === 0 ? (
        <p className={styles.empty}>아직 올린 레시피가 없어요.</p>
      ) : (
        <ul className={styles.list}>
          {recipes.map((recipe) => (
            <li key={recipe.id}>
              <div className={styles.itemHead}>
                {/* 승인 대기 중인 레시피는 다른 사람에게 안 보이지만 본인은 볼 수 있다. */}
                <Link className={styles.itemName} to={`/recipe/${recipe.id}`}>
                  {recipe.menu_name}
                </Link>
                <span
                  className={
                    recipe.status === 'approved'
                      ? `${styles.status} ${styles.approved}`
                      : styles.status
                  }
                >
                  {recipe.status === 'approved' ? '공개' : '승인 대기'}
                </span>
              </div>
              <p className={styles.itemMeta}>
                {recipe.category ?? '미분류'}
                {recipe.calorie !== null && ` · ${Math.round(recipe.calorie)} kcal`} · 추천{' '}
                {recipe.like_count}
              </p>
              <div className={styles.itemActions}>
                <button
                  className={styles.ghost}
                  type="button"
                  onClick={() => void startEdit(recipe.id)}
                >
                  수정
                </button>
                {/* 삭제는 레시피와 딸린 재료·조리순서를 함께 지우고 되돌릴 수 없다.
                    목록 안의 작은 버튼이라 잘못 누르기 쉬워서 한 번 묻는다. */}
                <button
                  className={styles.danger}
                  type="button"
                  onClick={() => {
                    if (window.confirm(`"${recipe.menu_name}"을 삭제할까요? 되돌릴 수 없어요.`)) {
                      void handleDelete(recipe.id)
                    }
                  }}
                >
                  삭제
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
