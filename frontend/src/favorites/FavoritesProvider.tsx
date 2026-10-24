import { useEffect, useMemo, type ReactNode } from 'react'

import { useAuth } from '../auth/context'
import { FavoritesContext } from './context'
import { createFavoritesStore } from './store'

export function FavoritesProvider({ children }: { children: ReactNode }) {
  const { userId } = useAuth()
  const store = useMemo(() => createFavoritesStore(userId), [userId])

  useEffect(() => () => store.dispose(), [store])

  return <FavoritesContext.Provider value={store}>{children}</FavoritesContext.Provider>
}
