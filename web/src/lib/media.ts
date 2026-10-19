import { useCallback, useSyncExternalStore } from 'react'

export function useMediaQuery(query: string): boolean {
  const subscribe = useCallback(
    (onChange: () => void) => {
      const list = window.matchMedia(query)
      list.addEventListener('change', onChange)
      return () => list.removeEventListener('change', onChange)
    },
    [query],
  )
  return useSyncExternalStore(subscribe, () => window.matchMedia(query).matches, () => false)
}

/** Phone-sized screens get drawers and full-screen panels instead of side columns. */
export function useIsPhone(): boolean {
  return !useMediaQuery('(min-width: 768px)')
}

/** Touch screens: no hover, and the on-screen keyboard shouldn't pop up by itself. */
export function useIsTouch(): boolean {
  return useMediaQuery('(pointer: coarse)')
}
