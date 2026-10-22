import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'

import { toHttps } from '../api/client'
import { listFavorites, toggleFavorite, type FavoriteItem } from '../api/favorites'
import { useAuth } from '../auth/context'
import Icon from './아이콘'
import styles from './FavoritesSection.module.css'

function FavoriteRow({ item, busy, onRemove }: { item: FavoriteItem; busy: boolean; onRemove: () => void }) {
  const imageUrl = toHttps(item.image_url)
  const [failedImage, setFailedImage] = useState<string | null>(null)
  const meta = [item.category, item.calorie === null ? null : `${Math.round(item.calorie)} kcal`].filter(Boolean).join(' · ')
  return <li className={styles.row} data-recipe-id={item.id}>
    <Link className={styles.recipe} to={`/recipe/${item.id}`}>
      <span className={styles.thumbnail}>
        {imageUrl && failedImage !== imageUrl
          ? <img src={imageUrl} alt="" width={72} height={72} loading="lazy" onError={() => setFailedImage(imageUrl)} />
          : <Icon name="bowl" size={28} />}
      </span>
      <span className={styles.text}>
        <span className={styles.title}>{item.menu_name}</span>
        {meta && <span className={styles.meta}>{meta}</span>}
      </span>
    </Link>
    <button className={styles.remove} type="button" aria-label={`즐겨찾기 해제: ${item.menu_name}`}
      disabled={busy} onClick={onRemove}><span aria-hidden="true">★</span></button>
  </li>
}

/** 마이의 최근 3개와 전체 화면이 같은 목록·해제·되돌리기를 사용한다. */
export default function FavoritesSection({ preview = false }: { preview?: boolean }) {
  const { userId } = useAuth()
  const [items, setItems] = useState<FavoriteItem[] | null>(null)
  const [loadError, setLoadError] = useState(false)
  const [retry, setRetry] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [removed, setRemoved] = useState<FavoriteItem | null>(null)
  const [notice, setNotice] = useState('')
  const [focusRecipe, setFocusRecipe] = useState<number | null>(null)
  const pending = useRef(false)
  const generation = useRef(0)
  const undoButton = useRef<HTMLButtonElement>(null)
  const list = useRef<HTMLUListElement>(null)

  useEffect(() => {
    generation.current += 1
    pending.current = false
    setBusy(false)
    setItems(null)
    setLoadError(false)
    setError(null)
    setRemoved(null)
    setNotice('')
    if (userId === null) return
    const controller = new AbortController()
    listFavorites(userId, controller.signal)
      .then(rows => {
        if (controller.signal.aborted) return
        if (!Array.isArray(rows)) throw new Error('즐겨찾기 목록 형식 오류')
        setItems(rows)
      })
      .catch(() => { if (!controller.signal.aborted) setLoadError(true) })
    return () => {
      controller.abort()
      generation.current += 1
    }
  }, [userId, retry])

  useLayoutEffect(() => {
    if (removed) undoButton.current?.focus()
    else if (focusRecipe !== null) list.current?.querySelector<HTMLButtonElement>(`[data-recipe-id="${focusRecipe}"] button`)?.focus()
  }, [removed, focusRecipe])

  async function change(item: FavoriteItem, restore = false) {
    if (userId === null || pending.current) return
    pending.current = true
    setBusy(true)
    setError(null)
    const version = generation.current
    try {
      const saved = await toggleFavorite(userId, item.id)
      if (version !== generation.current) return
      // 다른 기기에서 바뀌었을 수 있으므로 서버가 확인한 상태만 반영한다.
      if (saved !== restore) {
        setError('다른 화면에서 즐겨찾기 상태가 바뀌었어요. 다시 눌러주세요.')
        return
      }
      if (restore) {
        setItems(current => [item, ...(current ?? []).filter(row => row.id !== item.id)])
        setRemoved(null)
        setNotice('즐겨찾기에 다시 담았어요.')
        setFocusRecipe(item.id)
      } else {
        setItems(current => (current ?? []).filter(row => row.id !== item.id))
        setRemoved(item)
        setNotice(`${item.menu_name} 즐겨찾기를 해제했어요.`)
        setFocusRecipe(null)
      }
    } catch {
      if (version === generation.current) {
        setError(restore ? '즐겨찾기에 다시 담지 못했어요. 다시 시도해주세요.' : '즐겨찾기를 해제하지 못했어요. 다시 시도해주세요.')
      }
    } finally {
      if (version === generation.current) {
        pending.current = false
        setBusy(false)
      }
    }
  }

  const visible = preview ? items?.slice(0, 3) : items
  return <section className={styles.section} aria-label="즐겨찾기">
    <div className={styles.header}>
      {preview ? <h2>즐겨찾기</h2> : <p>저장한 레시피</p>}
      <div className={styles.headerActions}>
        {items !== null && items.length > 0 && <span>{items.length}개</span>}
        {preview && items !== null && items.length > 3 && <Link to="/my/favorites" className={styles.more} aria-label="즐겨찾기 더보기">
          더보기<Icon name="chevron-right" size={16} />
        </Link>}
      </div>
    </div>
    {loadError ? <div className={styles.feedback}>
      <p role="alert">즐겨찾기 목록을 불러오지 못했어요.</p>
      <button type="button" className={styles.action} onClick={() => setRetry(value => value + 1)}>즐겨찾기 다시 불러오기</button>
    </div> : items === null ? <p className={styles.empty} role="status">즐겨찾기를 불러오는 중…</p>
      : items.length === 0 ? <p className={styles.empty}>레시피 화면에서 <strong>즐겨찾기</strong>를 누르면 여기에 모여요.</p>
        : <ul ref={list} className={styles.list}>
          {visible?.map(item => <FavoriteRow key={item.id} item={item} busy={busy} onRemove={() => void change(item)} />)}
        </ul>}
    {error && <p className={styles.error} role="alert">{error}</p>}
    {notice && <div className={styles.feedback} role="status">
      <p>{notice}</p>
      {removed && <button ref={undoButton} className={styles.action} type="button" disabled={busy}
        onClick={() => void change(removed, true)}>되돌리기</button>}
    </div>}
  </section>
}
