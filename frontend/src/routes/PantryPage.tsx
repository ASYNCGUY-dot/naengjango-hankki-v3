import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { ApiError, TimeoutError } from '../api/client'
import {
  addPantryItem,
  describeExpiry,
  listPantry,
  removePantryItem,
  updateExpiry,
  type PantryItem,
} from '../api/pantry'
import { useAuth } from '../auth/context'
import { useSlowRequestHint } from '../hooks/useSlowRequestHint'
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
export default function PantryPage() {
  const { userId, isAuthenticated } = useAuth()
  const navigate = useNavigate()

  const [items, setItems] = useState<PantryItem[]>([])
  const [name, setName] = useState('')
  const [expiry, setExpiry] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [isAdding, setIsAdding] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const isSlow = useSlowRequestHint(isLoading)

  const load = useCallback(
    async (signal?: AbortSignal) => {
      if (userId === null) return
      setIsLoading(true)
      setError(null)
      try {
        setItems(await listPantry(userId, signal))
      } catch (caught) {
        if (signal?.aborted) return
        setError(describe(caught))
      } finally {
        if (!signal?.aborted) setIsLoading(false)
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

  async function handleAdd(event: FormEvent) {
    event.preventDefault()
    if (userId === null || isAdding) return
    const trimmed = name.trim()
    if (!trimmed) return

    setIsAdding(true)
    setError(null)
    try {
      await addPantryItem(userId, trimmed, expiry || null)
      setName('')
      setExpiry('')
      await load()
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
    <>
      <header className={styles.appbar}>
        <h1>내 냉장고</h1>
        {!isLoading && <span className={styles.count}>{items.length}개</span>}
      </header>

      <form className={styles.addForm} onSubmit={handleAdd}>
        <label className="sr-only" htmlFor="pantry-name">
          재료 이름
        </label>
        <input
          id="pantry-name"
          type="text"
          placeholder="재료 이름을 입력하세요"
          value={name}
          onChange={(e) => setName(e.target.value)}
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
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}

      {isLoading ? (
        <ul className={styles.list} aria-hidden="true">
          {Array.from({ length: 3 }, (_, index) => (
            <li key={index} className={styles.skeleton} />
          ))}
        </ul>
      ) : items.length === 0 ? (
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
    </>
  )
}
