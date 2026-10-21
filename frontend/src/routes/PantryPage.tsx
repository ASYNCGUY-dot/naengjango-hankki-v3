import { useCallback, useEffect, useLayoutEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { ApiError, TimeoutError } from '../api/client'
import {
  addPantryItem,
  describeExpiry,
  listPantry,
  removePantryItem,
  updateExpiry,
  suggestIngredients,
  type IngredientSuggestion,
  type PantryItem,
} from '../api/pantry'
import { useAuth } from '../auth/context'
import { useSlowRequestHint } from '../hooks/useSlowRequestHint'
import { useDeferredFocus } from '../hooks/비동기초점'
import styles from './PantryPage.module.css'

function describe(caught: unknown): string {
  if (caught instanceof ApiError || caught instanceof TimeoutError) return caught.message
  return '냉장고를 불러오지 못했어요. 잠시 후 다시 시도해주세요.'
}

/**
 * 냉장고 = 보유 재료 관리.
 *
 * 시안에는 수량 조절(− 3 +)이 있었지만 뺐다. ingredients 테이블에 수량 컬럼이 없고,
 * 추천 로직도 재료 "이름"만 쓴다. 화면에만 있고 아무 데도 안 가는 조작을 두면
 * 사용자는 그게 저장된다고 믿는다.
 *
 * 대신 유통기한을 앞세웠다. 서버가 임박 순으로 정렬해서 주고, "냉장고에서 곧 상하는 것부터
 * 쓰자"가 이 앱이 하려는 일에 더 가깝다.
 */
/** 입력할 때마다 요청하면 콜드스타트가 있는 서버에 과하다. 잠깐 멈추면 그때 보낸다. */
const SUGGEST_DEBOUNCE_MS = 250

export default function PantryPage() {
  const { userId, isAuthenticated } = useAuth()
  const navigate = useNavigate()

  const [items, setItems] = useState<PantryItem[]>([])
  const [name, setName] = useState('')
  const [expiry, setExpiry] = useState('')
  // 손으로 치면 "돼지 고기"처럼 어느 레시피 태그와도 안 맞는 값이 들어간다. 그러면
  // 추천이 나빠지는데 원인이 알고리즘인지 입력인지 구분할 수 없다.
  const [suggestions, setSuggestions] = useState<IngredientSuggestion[]>([])
  const [suggestionsOpen, setSuggestionsOpen] = useState(false)
  const [activeSuggestion, setActiveSuggestion] = useState(-1)
  const [suggestionStatus, setSuggestionStatus] = useState('')
  const nameInput = useRef<HTMLInputElement>(null)
  const removeButtons = useRef(new Map<number, HTMLButtonElement>())
  const pendingFocus = useRef<number | 'input' | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isAdding, setIsAdding] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const isSlow = useSlowRequestHint(isLoading)
  const { capture: captureFocus } = useDeferredFocus()

  const load = useCallback(
    async (signal?: AbortSignal, keepVisible = false) => {
      if (userId === null) return
      if (!keepVisible) setIsLoading(true)
      setError(null)
      try {
        setItems(await listPantry(userId, signal))
      } catch (caught) {
        if (signal?.aborted) return
        setError(describe(caught))
      } finally {
        if (!signal?.aborted && !keepVisible) setIsLoading(false)
      }
    },
    [userId],
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

  // 입력할 때마다 부르면 콜드스타트가 있는 서버에 과하다. 잠깐 멈추면 그때 보낸다.
  useEffect(() => {
    const keyword = name.trim()
    setActiveSuggestion(-1)
    setSuggestions([])
    if (keyword === '') {
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
            ? `추천 이름 ${rows.length}개. 위아래 방향키로 살펴보고 Enter로 선택하세요.`
            : '추천 이름이 없어요. 입력한 이름으로 추가할 수 있어요.')
        })
        .catch(() => {
          if (!controller.signal.aborted) setSuggestionStatus('추천 이름을 불러오지 못했어요. 입력한 이름으로 추가할 수 있어요.')
        })
    }, SUGGEST_DEBOUNCE_MS)
    return () => {
      clearTimeout(timer)
      controller.abort()
    }
  }, [name])

  useLayoutEffect(() => {
    if (pendingFocus.current === null) return
    const target = pendingFocus.current === 'input'
      ? nameInput.current
      : removeButtons.current.get(pendingFocus.current) ?? nameInput.current
    target?.focus()
    pendingFocus.current = null
  }, [items])

  function chooseSuggestion(value: string) {
    setName(value)
    setSuggestionsOpen(false)
    setActiveSuggestion(-1)
    nameInput.current?.focus()
  }

  function handleSuggestionKey(event: KeyboardEvent<HTMLInputElement>) {
    if (event.nativeEvent.isComposing) return
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
      chooseSuggestion(suggestions[activeSuggestion].name)
    }
  }

  async function handleAdd(event: FormEvent) {
    event.preventDefault()
    if (userId === null || isAdding) return
    const trimmed = name.trim()
    if (!trimmed) return

    const canRestore = captureFocus()
    const submittedName = name
    const submittedExpiry = expiry
    setIsAdding(true)
    setError(null)
    try {
      await addPantryItem(userId, trimmed, expiry || null)
      // 다음 재료를 입력하기 시작했다면 늦게 온 응답으로 그 입력을 지우지 않는다.
      setName((current) => current === submittedName ? '' : current)
      setExpiry((current) => current === submittedExpiry ? '' : current)
      if (nameInput.current?.value === submittedName) setSuggestionsOpen(false)
      // 기존 재료의 날짜를 고치는 중일 수 있어 재조회 때 목록을 스켈레톤으로 바꾸지 않는다.
      await load(undefined, true)
      if (canRestore()) nameInput.current?.focus()
    } catch (caught) {
      setError(describe(caught))
    } finally {
      setIsAdding(false)
    }
  }

  async function handleRemove(item: PantryItem) {
    if (userId === null) return
    // 지운 티가 바로 나야 한다. 콜드스타트가 있는 서버라 응답을 기다리면 눌러도 반응이
    // 없는 것처럼 보인다. 실패하면 다시 불러와 되돌린다.
    const before = items
    const index = items.findIndex((row) => row.id === item.id)
    pendingFocus.current = items[index + 1]?.id ?? items[index - 1]?.id ?? 'input'
    setItems((prev) => prev.filter((row) => row.id !== item.id))
    try {
      await removePantryItem(userId, item.id)
    } catch (caught) {
      setItems(before)
      setError(describe(caught))
    }
  }

  async function handleExpiryChange(item: PantryItem, value: string) {
    if (userId === null) return
    const before = items
    setItems((prev) =>
      prev.map((row) => (row.id === item.id ? { ...row, expiry_date: value || null } : row)),
    )
    try {
      await updateExpiry(userId, item.id, value || null)
    } catch (caught) {
      setItems(before)
      setError(describe(caught))
    }
  }

  if (!isAuthenticated) {
    // 로그인 화면으로 밀어내지 않는다. 둘러보다 들어온 사람이 왜 튕겼는지 모르게 된다.
    return (
      <div className={styles.guest}>
        <h1>내 냉장고</h1>
        <p>
          재료를 저장하려면 로그인이 필요해요.
          <br />
          로그인 없이도 레시피는 둘러볼 수 있어요.
        </p>
        <Link className={styles.cta} to="/login">
          로그인하러 가기
        </Link>
      </div>
    )
  }

  const soonCount = items.filter((item) => describeExpiry(item.expiry_date)?.isSoon).length

  return (
    <div className={styles.page}>
      <header className={styles.appbar}>
        <h1>내 냉장고</h1>
        {!isLoading && <span className={styles.count}>{items.length}개</span>}
      </header>

      <form className={styles.addForm} onSubmit={handleAdd} aria-busy={isAdding}>
        <label className="sr-only" htmlFor="pantry-name">
          재료 이름
        </label>
        <input
          id="pantry-name"
          ref={nameInput}
          type="text"
          role="combobox"
          aria-autocomplete="list"
          aria-expanded={suggestionsOpen && suggestions.length > 0}
          aria-controls="pantry-suggestions"
          aria-activedescendant={suggestionsOpen && activeSuggestion >= 0 ? `pantry-suggestion-${activeSuggestion}` : undefined}
          aria-describedby="pantry-suggestion-hint"
          autoComplete="off"
          placeholder="재료 이름을 입력하세요"
          value={name}
          onFocus={() => setSuggestionsOpen(true)}
          onBlur={() => setSuggestionsOpen(false)}
          onKeyDown={handleSuggestionKey}
          onChange={(e) => { setName(e.target.value); setSuggestionsOpen(true) }}
        />
        <label className="sr-only" htmlFor="pantry-expiry">
          유통기한
        </label>
        <input
          id="pantry-expiry"
          className={styles.dateInput}
          type="date"
          value={expiry}
          onChange={(e) => setExpiry(e.target.value)}
        />
        <button className={styles.addButton} type="submit" disabled={isAdding || !name.trim()}>
          {isAdding ? '추가 중…' : '추가'}
        </button>
      </form>
      <p id="pantry-suggestion-hint" className="sr-only">추천 이름을 고르거나 직접 입력한 재료를 추가할 수 있어요.</p>
      <p className="sr-only" role="status" aria-live="polite">{suggestionsOpen ? suggestionStatus : ''}</p>

      {/* 고르면 추천에서 반드시 매칭되는 이름들이다. 몇 개 레시피가 쓰는지 함께 보여줘야
          어느 표기를 골라야 할지 알 수 있다. */}
        <ul id="pantry-suggestions" className={styles.suggestions} role="listbox" aria-label="재료 추천" hidden={!suggestionsOpen || suggestions.length === 0}>
          {suggestions.map((item, index) => (
            <li key={item.name} role="presentation">
              <button type="button" role="option" id={`pantry-suggestion-${index}`} tabIndex={-1}
                aria-selected={activeSuggestion === index}
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => chooseSuggestion(item.name)}>
                <span>{item.name}</span>
                <span className={styles.suggestionCount}>레시피 {item.recipe_count}개</span>
              </button>
            </li>
          ))}
        </ul>

      {isSlow && (
        <p className={styles.notice} role="status">
          <span aria-hidden="true">☕</span>
          <span>
            서버를 깨우는 중이에요
            <small>무료 서버라 첫 요청은 30초쯤 걸려요.</small>
          </span>
        </p>
      )}

      {error !== null && (
        <div className={styles.error}>
          <p role="alert">{error}</p>
          <button className={styles.retry} type="button" onClick={() => void load()}>냉장고 다시 불러오기</button>
        </div>
      )}

      <p className="sr-only" role="status">{isLoading ? '냉장고 재료를 불러오는 중이에요.' : error === null ? `냉장고에 재료 ${items.length}개가 있어요.` : ''}</p>
      <div aria-busy={isLoading}>
      {isLoading ? (
        <ul className={styles.list} aria-hidden="true">
          {Array.from({ length: 3 }, (_, index) => (
            <li key={index} className={styles.skeleton} />
          ))}
        </ul>
      ) : items.length === 0 && error === null ? (
        <p className={styles.empty}>
          아직 넣어둔 재료가 없어요.
          <br />
          위에서 재료를 추가하면 그걸로 메뉴를 추천해드려요.
        </p>
      ) : (
        <ul className={styles.list}>
          {items.map((item) => {
            const expiryState = describeExpiry(item.expiry_date)
            return (
              <li key={item.id} className={styles.item}>
                <div className={styles.itemHeading}>
                <span className={styles.name}>{item.name}</span>

                {expiryState && (
                  <span
                    className={[
                      styles.expiry,
                      expiryState.isPast ? styles.expiryPast : '',
                      expiryState.isSoon ? styles.expirySoon : '',
                    ]
                      .filter(Boolean)
                      .join(' ')}
                  >
                    {expiryState.label}
                  </span>
                )}
                </div>

                <label className="sr-only" htmlFor={`expiry-${item.id}`}>
                  {item.name} 유통기한
                </label>
                <input
                  id={`expiry-${item.id}`}
                  className={styles.dateInput}
                  type="date"
                  value={item.expiry_date ?? ''}
                  onChange={(e) => void handleExpiryChange(item, e.target.value)}
                />

                <button
                  className={styles.iconButton}
                  ref={(element) => { if (element) removeButtons.current.set(item.id, element); else removeButtons.current.delete(item.id) }}
                  type="button"
                  aria-label={`${item.name} 삭제`}
                  onClick={() => void handleRemove(item)}
                >
                  ✕
                </button>
              </li>
            )
          })}
        </ul>
      )}
      </div>

      <div className={styles.sheet}>
        <p className={styles.summary}>
          <span>
            재료 {items.length}개{soonCount > 0 && ` · 유통기한 임박 ${soonCount}개`}
          </span>
        </p>
        <button
          className={styles.cta}
          type="button"
          disabled={items.length === 0}
          onClick={() => navigate('/recommend')}
        >
          이 재료로 추천받기
        </button>
      </div>
    </div>
  )
}
