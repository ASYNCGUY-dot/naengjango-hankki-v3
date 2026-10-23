import { useCallback, useEffect, useLayoutEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { Link } from 'react-router-dom'

import { ApiError, TimeoutError } from '../api/client'
import { listPantry, suggestIngredients, type IngredientSuggestion } from '../api/pantry'
import {
  describeMatch,
  describeMissing,
  getRecommendations,
  matchLevel,
  type RecommendationItem,
} from '../api/recommend'
import RecipeCard from '../components/RecipeCard'
import { useAuth } from '../auth/context'
import { useSlowRequestHint } from '../hooks/useSlowRequestHint'
import styles from './RecommendPage.module.css'

function describe(caught: unknown): string {
  if (caught instanceof ApiError || caught instanceof TimeoutError) return caught.message
  return '추천을 받아오지 못했어요. 잠시 후 다시 시도해주세요.'
}

/** 순서가 달라도 같은 재료 구성이면 같은 것으로 본다 - 서버에 보내는 결과가 같기 때문이다. */
function sameSet(a: string[], b: string[]): boolean {
  return a.length === b.length && [...a].sort().join('\0') === [...b].sort().join('\0')
}

/**
 * 추천 결과.
 *
 * 서버가 냉장고를 스스로 읽지 않으므로 화면이 먼저 냉장고를 조회한 뒤 재료 이름을 넘긴다.
 * 그래서 /recommend 주소를 직접 열어도 동작한다 - 냉장고 화면을 거쳐 넘어온 상태에
 * 의존하지 않는다.
 *
 * 기준 재료를 이 화면에서 바로 고칠 수 있다(2026-08-18). 그전에는 냉장고에 저장된 재료를
 * 그대로 쓰기만 해서, "오늘은 이 재료만으로 뭘 만들지" 같은 걸 보려면 냉장고에 가서
 * 실제 재료를 지웠다가 되돌려야 했다. 여기서 고치는 것은 이번 추천에만 쓰이고 냉장고를
 * 건드리지 않는다. 서버는 원래부터 임의의 재료 목록을 받도록 되어 있어(라우터 주석 참고)
 * 백엔드 변경은 없다.
 *
 * 재료를 고칠 때마다 자동으로 다시 부르지는 않는다. 추천 한 번이 무료 티어에서 2.4초라
 * 칩 하나 지울 때마다 그만큼 기다리면 편집 자체가 괴로워진다. 다 고친 뒤 버튼으로 부른다.
 *
 * 이 화면이 부르는 API가 가장 느리다. 콜드스타트에 더해 추천 계산 자체가 서버에서
 * 몇 초 걸린다(Render 무료 티어 0.1 CPU 기준 실측 2.4초, 캐시 적용 후 로컬 0.2초).
 */
export default function RecommendPage() {
  const { userId, isAuthenticated } = useAuth()

  const [items, setItems] = useState<RecommendationItem[]>([])
  // 냉장고에 저장된 것. "되돌리기"의 기준이라 편집해도 그대로 둔다.
  const [pantryNames, setPantryNames] = useState<string[]>([])
  // 지금 편집 중인 목록.
  const [ingredients, setIngredients] = useState<string[]>([])
  // 화면에 보이는 결과를 만들어낸 목록. 이것과 위가 다르면 결과가 낡은 것이다.
  const [appliedIngredients, setAppliedIngredients] = useState<string[]>([])
  const [draft, setDraft] = useState('')
  const [suggestions, setSuggestions] = useState<IngredientSuggestion[]>([])
  const [suggestionsOpen, setSuggestionsOpen] = useState(false)
  const [activeSuggestion, setActiveSuggestion] = useState(-1)
  const [suggestionStatus, setSuggestionStatus] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const ingredientInput = useRef<HTMLInputElement>(null)
  const removeButtons = useRef(new Map<string, HTMLButtonElement>())
  const pendingFocus = useRef<string | null>(null)
  const [editingStatus, setEditingStatus] = useState('')
  const isSlow = useSlowRequestHint(isLoading)

  const recommend = useCallback(
    async (names: string[], signal?: AbortSignal) => {
      if (userId === null) return
      setIsLoading(true)
      setError(null)
      try {
        // 재료가 없으면 추천을 부르지 않는다. 서버가 후보 1,144개를 다 계산하고
        // 아무 재료도 안 맞는 목록을 돌려주는데, 그걸 보여줄 이유가 없다.
        if (names.length === 0) {
          setItems([])
          setAppliedIngredients([])
          return
        }
        setItems(await getRecommendations(userId, names, signal))
        setAppliedIngredients(names)
      } catch (caught) {
        if (signal?.aborted) return
        setError(describe(caught))
        setItems([])
      } finally {
        if (!signal?.aborted) setIsLoading(false)
      }
    },
    [userId],
  )

  const load = useCallback(
    async (signal?: AbortSignal) => {
      if (userId === null) return
      setIsLoading(true)
      setError(null)
      try {
        const pantry = await listPantry(userId, signal)
        const names = pantry.map((item) => item.name)
        setPantryNames(names)
        setIngredients(names)
        await recommend(names, signal)
      } catch (caught) {
        if (signal?.aborted) return
        setError(describe(caught))
        setItems([])
        setIsLoading(false)
      }
    },
    [userId, recommend],
  )

  useEffect(() => {
    if (userId === null) {
      setIsLoading(false)
      return
    }
    const controller = new AbortController()
    void load(controller.signal)
    return () => controller.abort()
  }, [userId, load])

  // 냉장고 화면과 같은 API로 실제 레시피에 쓰이는 재료 이름을 제안한다.
  useEffect(() => {
    const keyword = draft.trim()
    setSuggestions([])
    setActiveSuggestion(-1)
    if (!keyword || !isAuthenticated) {
      setSuggestionStatus('')
      return
    }
    const controller = new AbortController()
    setSuggestionStatus('재료 이름을 찾는 중이에요.')
    const timer = setTimeout(() => {
      suggestIngredients(keyword, controller.signal)
        .then((rows) => {
          if (controller.signal.aborted) return
          setSuggestions(rows)
          setSuggestionStatus(rows.length > 0
            ? `추천 이름 ${rows.length}개. 클릭하거나 위아래 방향키와 Enter로 추가하세요.`
            : '추천 이름이 없어요. 입력한 이름으로 추가할 수 있어요.')
        })
        .catch(() => {
          if (!controller.signal.aborted) {
            setSuggestionStatus('추천 이름을 불러오지 못했어요. 입력한 이름으로 추가할 수 있어요.')
          }
        })
    }, 250)
    return () => {
      clearTimeout(timer)
      controller.abort()
    }
  }, [draft, isAuthenticated])

  function chooseIngredient(value: string) {
    const name = value.trim()
    if (!name) return
    // 같은 재료를 두 번 넣으면 서버가 겹침 개수를 부풀려 센다.
    if (!ingredients.includes(name)) {
      setIngredients((prev) => [...prev, name])
      setEditingStatus(`${name} 추가. 기준 재료 ${ingredients.length + 1}개.`)
    } else {
      setEditingStatus(`${name}은 이미 기준 재료에 있어요.`)
    }
    setDraft('')
    ingredientInput.current?.focus()
    setSuggestionsOpen(false)
    setActiveSuggestion(-1)
  }

  function addIngredient(event: FormEvent) {
    event.preventDefault()
    chooseIngredient(draft)
  }

  function handleSuggestionKey(event: KeyboardEvent<HTMLInputElement>) {
    // 한글 조합을 확정하는 Enter가 재료 추가까지 실행하지 않게 한다.
    if (event.nativeEvent.isComposing || event.nativeEvent.keyCode === 229) {
      if (event.key === 'Enter') event.preventDefault()
      return
    }
    if (event.key === 'Escape') {
      setSuggestionsOpen(false)
      setActiveSuggestion(-1)
    } else if ((event.key === 'ArrowDown' || event.key === 'ArrowUp') && suggestions.length > 0) {
      event.preventDefault()
      setSuggestionsOpen(true)
      setActiveSuggestion((current) => event.key === 'ArrowDown'
        ? (current + 1) % suggestions.length
        : (current <= 0 ? suggestions.length - 1 : current - 1))
    } else if (event.key === 'Enter' && suggestionsOpen && activeSuggestion >= 0) {
      event.preventDefault()
      chooseIngredient(suggestions[activeSuggestion].name)
    }
  }

  function removeIngredient(name: string) {
    const index = ingredients.indexOf(name)
    pendingFocus.current = ingredients[index + 1] ?? ingredients[index - 1] ?? ''
    setIngredients((prev) => prev.filter((value) => value !== name))
    setEditingStatus(`${name} 제외. 기준 재료 ${ingredients.length - 1}개.`)
  }

  useLayoutEffect(() => {
    if (pendingFocus.current === null) return
    const target = removeButtons.current.get(pendingFocus.current) ?? ingredientInput.current
    target?.focus()
    pendingFocus.current = null
  }, [ingredients])

  const isDirty = !sameSet(ingredients, appliedIngredients)
  const isEdited = !sameSet(ingredients, pantryNames)

  if (!isAuthenticated) {
    return (
      <div className={styles.guest}>
        <h1>나를 위한 레시피 추천</h1>
        <p>
          냉장고 재료로 추천을 받으려면 로그인이 필요해요.
          <br />
          로그인 없이도 레시피는 둘러볼 수 있어요.
        </p>
        <Link className={styles.cta} to="/login">
          로그인하러 가기
        </Link>
      </div>
    )
  }

  return (
    <div className={styles.page}>
      <header className={styles.appbar}>
        <h1>나를 위한 레시피 추천</h1>
        {/* 편집한 뒤에만 나타난다. 안 고친 상태에서 "되돌리기"는 아무 일도 안 하는
            버튼이라 자리만 차지한다. */}
        {isEdited && (
          <button
            className={styles.reset}
            type="button"
            onClick={() => {
              setIngredients(pantryNames)
              setDraft('')
              pendingFocus.current = ''
              setEditingStatus(`냉장고 재료 ${pantryNames.length}개로 되돌렸어요.`)
            }}
          >
            냉장고 재료로 되돌리기
          </button>
        )}
      </header>

      <section className={styles.basis} aria-labelledby="basis-heading">
        <h2 className={styles.basisLabel} id="basis-heading">
          기준 재료
        </h2>
        <p className={styles.basisHint}>
          여기서 고친 재료는 이번 추천에만 쓰이고 냉장고는 그대로예요.
        </p>

        {ingredients.length > 0 && (
          <ul className={styles.chips}>
            {ingredients.map((name) => (
              <li key={name}>
                <span className={styles.chip}>
                  {name}
                  <button
                    type="button"
                    className={styles.chipRemove}
                    aria-label={`${name} 빼기`}
                    ref={(element) => { if (element) removeButtons.current.set(name, element); else removeButtons.current.delete(name) }}
                    onClick={() => removeIngredient(name)}
                  >
                    <span aria-hidden="true">×</span>
                  </button>
                </span>
              </li>
            ))}
          </ul>
        )}

        <form className={styles.addRow} onSubmit={addIngredient}>
          <label className={styles.srOnly} htmlFor="add-ingredient">
            재료 추가
          </label>
          <input
            id="add-ingredient"
            ref={ingredientInput}
            type="text"
            role="combobox"
            autoComplete="off"
            aria-autocomplete="list"
            aria-expanded={suggestionsOpen && suggestions.length > 0}
            aria-controls="recommend-suggestions"
            aria-activedescendant={suggestionsOpen && activeSuggestion >= 0 ? `recommend-suggestion-${activeSuggestion}` : undefined}
            aria-describedby="recommend-suggestion-hint"
            placeholder="재료를 입력하세요"
            value={draft}
            onChange={(e) => {
              setDraft(e.target.value)
              setSuggestions([])
              setActiveSuggestion(-1)
              setSuggestionsOpen(true)
            }}
            onFocus={() => setSuggestionsOpen(true)}
            onBlur={() => {
              setSuggestionsOpen(false)
              setActiveSuggestion(-1)
            }}
            onKeyDown={handleSuggestionKey}
          />
          <button type="submit" disabled={draft.trim() === ''}>
            추가
          </button>
        </form>
        <ul id="recommend-suggestions" className={styles.suggestions} role="listbox" aria-label="재료 추천" hidden={!suggestionsOpen || suggestions.length === 0}>
          {suggestions.map((suggestion, index) => (
            <li key={suggestion.name} role="presentation">
              <button
                type="button"
                role="option"
                id={`recommend-suggestion-${index}`}
                tabIndex={-1}
                aria-selected={activeSuggestion === index}
                onPointerDown={(event) => event.preventDefault()}
                onClick={() => chooseIngredient(suggestion.name)}
              >
                <span>{suggestion.name}</span>
                <span className={styles.suggestionCount}>레시피 {suggestion.recipe_count}개</span>
              </button>
            </li>
          ))}
        </ul>
        <p id="recommend-suggestion-hint" className="sr-only">추천 이름을 선택해 추가하거나 직접 입력한 재료를 추가할 수 있어요.</p>
        <p className={styles.suggestionStatus} role="status">{suggestionsOpen ? suggestionStatus : ''}</p>
        <p className="sr-only" role="status">{editingStatus}</p>

        {/* 결과가 낡았을 때만 보여준다. 항상 있으면 눌러야 하는지 아닌지가 안 보인다. */}
        {isDirty && (
          <button
            className={styles.apply}
            type="button"
            disabled={isLoading}
            onClick={() => void recommend(ingredients)}
          >
            {ingredients.length === 0 ? '재료를 하나 이상 넣어주세요' : '이 재료로 추천받기'}
          </button>
        )}
      </section>

      {isSlow && (
        <p className={styles.notice} role="status">
          <span aria-hidden="true">☕</span>
          <span>
            메뉴를 고르는 중이에요
            <small>재료를 레시피 1,100여 개와 맞춰보고 있어요. 잠시만요.</small>
          </span>
        </p>
      )}

      {error !== null && (
        <div className={styles.error}>
          <p role="alert">{error}</p>
          <button className={styles.reset} type="button" onClick={() => void (ingredients.length > 0 ? recommend(ingredients) : load())}>추천 다시 불러오기</button>
        </div>
      )}

      <p className="sr-only" role="status">{isLoading ? '재료에 맞는 메뉴를 찾는 중이에요.' : error === null ? `추천 메뉴 ${items.length}개를 찾았어요.` : ''}</p>
      <div aria-busy={isLoading}>
      {isLoading ? (
        <ul className={styles.grid} aria-hidden="true">
          {Array.from({ length: 4 }, (_, index) => (
            <li key={index} className={styles.skeleton} />
          ))}
        </ul>
      ) : appliedIngredients.length === 0 && error === null ? (
        <div className={styles.empty}>
          <p>
            {pantryNames.length === 0
              ? '냉장고가 비어 있어요. 위에 재료를 넣거나 냉장고를 채워보세요.'
              : '기준 재료가 비었어요. 위에 재료를 넣고 추천을 받아보세요.'}
          </p>
          {pantryNames.length === 0 && (
            <Link className={styles.cta} to="/pantry">
              냉장고 채우러 가기
            </Link>
          )}
        </div>
      ) : items.length === 0 && error === null ? (
        <p className={styles.empty}>맞는 메뉴를 찾지 못했어요. 재료를 더 넣어보세요.</p>
      ) : (
        <ul className={styles.grid}>
          {items.map((item) => (
            <li key={item.id}>
              <RecipeCard
                recipe={item}
                badge={{ text: describeMatch(item), tone: matchLevel(item) }}
                note={describeMissing(item)}
              />
            </li>
          ))}
        </ul>
      )}
      </div>

      {!isLoading && items.length > 0 && (
        <p className={styles.footnote}>
          보유 재료를 잘 쓰는 순서예요. 아래로 갈수록 겹치는 재료가 적어요.
        </p>
      )}
    </div>
  )
}
