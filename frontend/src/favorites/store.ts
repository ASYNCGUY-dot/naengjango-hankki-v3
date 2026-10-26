import { listFavorites, toggleFavorite, type FavoriteItem } from '../api/favorites'

export type FavoritesSnapshot = {
  isReady: boolean
  loadError: boolean
  favoriteIds: ReadonlySet<number>
  busyIds: ReadonlySet<number>
  errors: ReadonlyMap<number, string>
}

function emptySnapshot(): FavoritesSnapshot {
  return {
    isReady: false,
    loadError: false,
    favoriteIds: new Set(),
    busyIds: new Set(),
    errors: new Map(),
  }
}

/** 같은 레시피가 여러 목록에 나타나도 조회와 변경 상태를 한 곳에서 관리한다. */
export function createFavoritesStore(userId: number | null) {
  let snapshot = emptySnapshot()
  const listeners = new Set<() => void>()
  let loading = false
  let controller: AbortController | null = null
  let listVersion = 0
  let generation = 0

  function publish(next: FavoritesSnapshot) {
    snapshot = next
    listeners.forEach(listener => listener())
  }

  function stopLoading() {
    listVersion += 1
    controller?.abort()
    controller = null
    loading = false
  }

  function syncFavorites(items: FavoriteItem[]) {
    stopLoading()
    const favoriteIds = new Set(items.map(item => item.id))
    // 마이 목록 조회가 진행 중인 카드 토글의 낙관적 표시를 덮어쓰지 않는다.
    snapshot.busyIds.forEach(id => {
      if (snapshot.favoriteIds.has(id)) favoriteIds.add(id)
      else favoriteIds.delete(id)
    })
    publish({ ...snapshot, isReady: true, loadError: false, favoriteIds })
  }

  function syncFavorite(recipeId: number, saved: boolean) {
    const favoriteIds = new Set(snapshot.favoriteIds)
    if (saved) favoriteIds.add(recipeId)
    else favoriteIds.delete(recipeId)
    const errors = new Map(snapshot.errors)
    errors.delete(recipeId)
    publish({ ...snapshot, favoriteIds, errors })
  }

  function load(force = false) {
    if (userId === null || loading || (!force && (snapshot.isReady || snapshot.loadError))) return
    loading = true
    controller = new AbortController()
    const signal = controller.signal
    const version = ++listVersion
    const requestGeneration = generation
    publish({ ...snapshot, isReady: false, loadError: false })
    void listFavorites(userId, signal)
      .then(items => {
        if (signal.aborted || version !== listVersion || requestGeneration !== generation) return
        if (!Array.isArray(items)) throw new Error('즐겨찾기 목록 형식 오류')
        syncFavorites(items)
      })
      .catch(() => {
        if (signal.aborted || version !== listVersion || requestGeneration !== generation) return
        loading = false
        controller = null
        publish({ ...snapshot, isReady: false, loadError: true })
      })
  }

  async function toggle(recipeId: number): Promise<boolean | undefined> {
    if (userId === null || !snapshot.isReady || snapshot.busyIds.has(recipeId)) return
    const requestGeneration = generation
    const wasFavorited = snapshot.favoriteIds.has(recipeId)
    const busyIds = new Set(snapshot.busyIds)
    busyIds.add(recipeId)
    const errors = new Map(snapshot.errors)
    errors.delete(recipeId)
    const favoriteIds = new Set(snapshot.favoriteIds)
    if (wasFavorited) favoriteIds.delete(recipeId)
    else favoriteIds.add(recipeId)
    publish({ ...snapshot, favoriteIds, busyIds, errors })
    try {
      const saved = await toggleFavorite(userId, recipeId)
      if (requestGeneration !== generation) return
      syncFavorite(recipeId, saved)
      return saved
    } catch {
      if (requestGeneration !== generation) return
      const rollbackIds = new Set(snapshot.favoriteIds)
      if (wasFavorited) rollbackIds.add(recipeId)
      else rollbackIds.delete(recipeId)
      const nextErrors = new Map(snapshot.errors)
      nextErrors.set(recipeId, '즐겨찾기에 담지 못했어요. 잠시 후 다시 시도해주세요.')
      publish({ ...snapshot, favoriteIds: rollbackIds, errors: nextErrors })
      return undefined
    } finally {
      if (requestGeneration === generation) {
        const nextBusyIds = new Set(snapshot.busyIds)
        nextBusyIds.delete(recipeId)
        publish({ ...snapshot, busyIds: nextBusyIds })
      }
    }
  }

  return {
    getSnapshot: () => snapshot,
    subscribe(listener: () => void) {
      listeners.add(listener)
      return () => { listeners.delete(listener) }
    },
    ensureLoaded: () => load(),
    retry: () => load(true),
    toggle,
    syncFavorites,
    syncFavorite,
    dispose() {
      // 로그아웃, 사용자 변경, 언마운트 후 이전 요청이 상태를 되살리지 않게 한다.
      generation += 1
      stopLoading()
      snapshot = emptySnapshot()
    },
  }
}

export type FavoritesStore = ReturnType<typeof createFavoritesStore>
