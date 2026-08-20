import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import { ApiError, TimeoutError, toHttps } from '../api/client'
import { MAX_PHOTO_BYTES, createBrag, shrinkForUpload, uploadBragPhoto } from '../api/brags'
import { getRecipe } from '../api/recipeDetail'
import { searchRecipes, type RecipeSummary } from '../api/recipes'
import { useAuth } from '../auth/context'
import styles from './BragWritePage.module.css'

/** 입력할 때마다 부르면 콜드스타트가 있는 서버에 과하다. 잠깐 멈추면 그때 보낸다. */
const SEARCH_DEBOUNCE_MS = 400

function describe(caught: unknown): string {
  if (caught instanceof ApiError || caught instanceof TimeoutError) return caught.message
  if (caught instanceof Error) return caught.message
  return '자랑을 올리지 못했어요. 잠시 후 다시 시도해주세요.'
}

/**
 * 자랑 글쓰기.
 *
 * 들어오는 길이 둘이다. 자랑하기 탭의 글쓰기 버튼으로 오면 레시피를 검색해 고르고,
 * 레시피 상세의 "이거 만들었어요"로 오면 ?recipe=67로 이미 골라진 채 온다. 후자가
 * 진짜 목적이다 - 만들고 나서 그 화면을 보고 있을 때 바로 올리게 된다.
 *
 * 사진은 글보다 먼저 올린다. 무료 서버에서 업로드가 느린데 한 요청에 묶으면 실패했을
 * 때 쓴 글이 통째로 날아간다.
 */
export default function BragWritePage() {
  const { userId } = useAuth()
  const navigate = useNavigate()
  const [params] = useSearchParams()

  const [recipe, setRecipe] = useState<{ id: number; menu_name: string } | null>(null)
  const [keyword, setKeyword] = useState('')
  const [results, setResults] = useState<RecipeSummary[]>([])

  const [body, setBody] = useState('')
  const [photo, setPhoto] = useState<File | null>(null)
  const [preview, setPreview] = useState<string | null>(null)

  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // 레시피 상세에서 넘어온 경우. 이름을 보여주려면 한 번 읽어야 한다.
  const preselected = Number(params.get('recipe'))
  useEffect(() => {
    if (!Number.isInteger(preselected) || preselected <= 0) return
    const controller = new AbortController()
    getRecipe(preselected, controller.signal)
      .then((detail) => setRecipe({ id: detail.id, menu_name: detail.menu_name }))
      // 못 읽으면 그냥 검색으로 고르게 둔다.
      .catch(() => {})
    return () => controller.abort()
  }, [preselected])

  useEffect(() => {
    if (recipe !== null || keyword.trim() === '') {
      setResults([])
      return
    }
    const timer = setTimeout(() => {
      searchRecipes({ keyword })
        .then((rows) => setResults(rows.slice(0, 8)))
        .catch(() => setResults([]))
    }, SEARCH_DEBOUNCE_MS)
    return () => clearTimeout(timer)
  }, [keyword, recipe])

  // 미리보기 주소는 다 쓰면 풀어준다. 안 그러면 페이지를 떠도 메모리에 남는다.
  useEffect(() => {
    if (photo === null) {
      setPreview(null)
      return
    }
    const url = URL.createObjectURL(photo)
    setPreview(url)
    return () => URL.revokeObjectURL(url)
  }, [photo])

  function handlePick(file: File | undefined) {
    setError(null)
    if (file === undefined) return
    // 브라우저에서 줄여 보내지만, 원본이 터무니없이 크면 줄이는 것부터가 느리다.
    if (file.size > MAX_PHOTO_BYTES * 10) {
      setError('사진이 너무 커요. 다른 사진을 골라주세요.')
      return
    }
    setPhoto(file)
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    if (userId === null || recipe === null || body.trim() === '') return

    setIsSaving(true)
    setError(null)
    try {
      let imageUrl: string | null = null
      if (photo !== null) {
        imageUrl = await uploadBragPhoto(userId, await shrinkForUpload(photo))
      }
      await createBrag(userId, { recipe_id: recipe.id, body: body.trim(), image_url: imageUrl })
      navigate('/brags', { replace: true })
    } catch (caught) {
      setError(describe(caught))
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <div className={styles.page}>
      <h1>자랑하기</h1>

      {error !== null && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}

      <form className={styles.form} onSubmit={(event) => void handleSubmit(event)}>
        <span className={styles.label}>무엇을 만들었나요?</span>
        {recipe === null ? (
          <>
            <label className="sr-only" htmlFor="brag-recipe-search">
              레시피 검색
            </label>
            <input
              id="brag-recipe-search"
              type="search"
              className={styles.input}
              placeholder="레시피 이름으로 찾기"
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
            />
            {results.length > 0 && (
              <ul className={styles.results}>
                {results.map((item) => (
                  <li key={item.id}>
                    <button
                      type="button"
                      className={styles.result}
                      onClick={() => {
                        setRecipe({ id: item.id, menu_name: item.menu_name })
                        setKeyword('')
                      }}
                    >
                      {item.menu_name}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </>
        ) : (
          <div className={styles.picked}>
            <span>{recipe.menu_name}</span>
            <button type="button" className={styles.change} onClick={() => setRecipe(null)}>
              바꾸기
            </button>
          </div>
        )}

        <label className={styles.label} htmlFor="brag-photo">
          사진 (선택)
        </label>
        {/* capture를 안 붙인다. 붙이면 카메라만 열려서 이미 찍어둔 사진을 못 고른다. */}
        <input
          id="brag-photo"
          type="file"
          className={styles.input}
          accept="image/jpeg,image/png,image/webp"
          onChange={(event) => handlePick(event.target.files?.[0])}
        />
        {preview !== null && (
          <img className={styles.preview} src={toHttps(preview) ?? preview} alt="올릴 사진 미리보기" />
        )}

        <label className={styles.label} htmlFor="brag-body">
          어땠나요?
        </label>
        <textarea
          id="brag-body"
          className={styles.textarea}
          rows={5}
          maxLength={1000}
          value={body}
          placeholder="만들면서 바꾼 것, 다음에 해볼 것을 적어주세요."
          onChange={(event) => setBody(event.target.value)}
        />

        <div className={styles.actions}>
          <button
            className={styles.primary}
            type="submit"
            disabled={isSaving || recipe === null || body.trim() === ''}
          >
            {isSaving ? '올리는 중…' : '올리기'}
          </button>
          <button
            className={styles.ghost}
            type="button"
            onClick={() => navigate('/brags')}
            disabled={isSaving}
          >
            취소
          </button>
        </div>
        {isSaving && photo !== null && (
          <p className={styles.hint} role="status">
            사진을 올리는 중이에요. 무료 서버라 조금 걸릴 수 있어요.
          </p>
        )}
      </form>
    </div>
  )
}
