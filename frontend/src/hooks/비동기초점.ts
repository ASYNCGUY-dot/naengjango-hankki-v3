import { useCallback, useEffect, useRef } from 'react'

/**
 * 요청을 시작할 때 capture()를 호출하고, 응답을 반영한 뒤 반환 함수가 참일 때만
 * 초점을 복귀한다. 기다리는 중의 사용자 탐색·입력과 더 최신 요청을 우선한다.
 */
export function useDeferredFocus() {
  const mounted = useRef(false)
  const interaction = useRef(0)
  const request = useRef(0)

  useEffect(() => {
    mounted.current = true
    const cancel = () => { interaction.current += 1 }
    const events = ['pointerdown', 'keydown', 'focusin', 'wheel', 'touchstart'] as const
    for (const event of events) document.addEventListener(event, cancel, { capture: true, passive: true })
    return () => {
      mounted.current = false
      request.current += 1
      for (const event of events) document.removeEventListener(event, cancel, true)
    }
  }, [])

  const capture = useCallback(() => {
    const interactionAtStart = interaction.current
    const requestAtStart = ++request.current
    return () => mounted.current
      && request.current === requestAtStart
      && interaction.current === interactionAtStart
  }, [])

  return { capture }
}
