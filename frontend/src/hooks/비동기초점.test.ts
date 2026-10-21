import { fireEvent, renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { useDeferredFocus } from './비동기초점'

describe('비동기 작업 후 초점 복귀', () => {
  it.each(['pointerdown', 'keydown', 'focusin', 'wheel', 'touchstart'])(
    '대기 중 %s 조작이 있으면 자동 복귀를 취소한다',
    (event) => {
      const { result } = renderHook(() => useDeferredFocus())
      const canRestore = result.current.capture()
      expect(canRestore()).toBe(true)
      fireEvent(document, new Event(event, { bubbles: true }))
      expect(canRestore()).toBe(false)
    },
  )

  it('더 최신 요청이 시작되면 이전 요청은 초점을 가져오지 않는다', () => {
    const { result } = renderHook(() => useDeferredFocus())
    const first = result.current.capture()
    const latest = result.current.capture()
    expect(first()).toBe(false)
    expect(latest()).toBe(true)
  })

  it('화면을 떠나면 남아 있는 응답은 초점을 바꾸지 못한다', () => {
    const { result, unmount } = renderHook(() => useDeferredFocus())
    const canRestore = result.current.capture()
    unmount()
    expect(canRestore()).toBe(false)
  })
})
