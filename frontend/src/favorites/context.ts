import { createContext, useContext, useEffect, useMemo, useSyncExternalStore } from 'react'

import type { FavoritesStore } from './store'

export const FavoritesContext = createContext<FavoritesStore | null>(null)

export function useFavorites({ load = true }: { load?: boolean } = {}) {
  const store = useContext(FavoritesContext)
  if (store === null) throw new Error('useFavorites는 FavoritesProvider 안에서만 쓸 수 있습니다.')
  const snapshot = useSyncExternalStore(store.subscribe, store.getSnapshot, store.getSnapshot)

  useEffect(() => {
    if (load) store.ensureLoaded()
  }, [load, store])

  return useMemo(() => ({
    ...snapshot,
    retry: store.retry,
    toggle: store.toggle,
    syncFavorites: store.syncFavorites,
    syncFavorite: store.syncFavorite,
  }), [snapshot, store])
}
