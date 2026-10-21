import { useLayoutEffect, useState } from 'react'
import { act, fireEvent, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Link, Route, Routes, useNavigate } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import RouteExperience from './화면이동'
import { renderWithProviders } from '../test/renderWithProviders'

let currentScroll = 0
let documentHeight = 2400
let shrinkOnDetail = false

function Detail() {
  const navigate = useNavigate()
  // 긴 목록이 짧은 상세 로딩 화면으로 바뀌면 브라우저가 스크롤을 0으로 제한한다.
  // 새 화면의 레이아웃 시점에 발생해 이전 화면의 passive effect보다 먼저 도착할 수 있다.
  useLayoutEffect(() => {
    if (shrinkOnDetail) {
      currentScroll = 0
      window.dispatchEvent(new Event('scroll'))
    }
  }, [])
  return <><h1>레시피 상세</h1><button type="button" onClick={() => navigate(-1)}>뒤로</button></>
}

function Home({ delayed = false }: { delayed?: boolean }) {
  const [ready, setReady] = useState(!delayed)
  return <>
    <h1>집밥 목록</h1>
    {ready ? <p>불러온 집밥 글</p> : <p role="status">불러오는 중</p>}
    <button type="button" onClick={() => setReady(true)}>목록 불러오기</button>
    <Link to="/recipe/1">레시피 보기</Link>
  </>
}

function renderRoutes({ delayed = false } = {}) {
  return renderWithProviders(<RouteExperience><Routes>
    <Route path="/" element={<Home delayed={delayed} />} />
    <Route path="/recipe/1" element={<Detail />} />
  </Routes></RouteExperience>)
}

describe('화면 이동 스크롤 복원', () => {
  beforeEach(() => {
    localStorage.clear()
    currentScroll = 0
    documentHeight = 2400
    shrinkOnDetail = false
    vi.spyOn(window, 'scrollY', 'get').mockImplementation(() => currentScroll)
    vi.spyOn(window, 'innerHeight', 'get').mockReturnValue(600)
    vi.spyOn(document.documentElement, 'scrollHeight', 'get').mockImplementation(() => documentHeight)
    vi.spyOn(window, 'scrollTo').mockImplementation((options: number | ScrollToOptions) => {
      if (typeof options !== 'object') return
      currentScroll = Math.max(0, Math.min(options.top ?? 0, documentHeight - window.innerHeight))
      window.dispatchEvent(new Event('scroll'))
    })
  })
  afterEach(() => vi.restoreAllMocks())

  it('이전 화면을 제거하면서 발생한 스크롤 제한이 저장된 위치를 지우지 않는다', async () => {
    const user = userEvent.setup()
    shrinkOnDetail = true
    renderRoutes()
    currentScroll = 1024
    fireEvent.scroll(window)

    await user.click(screen.getByRole('link', { name: '레시피 보기' }))
    expect(currentScroll).toBe(0)
    await user.click(screen.getByRole('button', { name: '뒤로' }))

    expect(currentScroll).toBe(1024)
    expect(screen.getByRole('heading', { name: '집밥 목록' })).toHaveFocus()
  })

  it('뒤로 온 목록이 비동기로 길어진 후에도 원래 위치까지 복원한다', async () => {
    const user = userEvent.setup()
    renderRoutes({ delayed: true })
    currentScroll = 1024
    fireEvent.scroll(window)
    await user.click(screen.getByRole('link', { name: '레시피 보기' }))
    documentHeight = 700
    await user.click(screen.getByRole('button', { name: '뒤로' }))
    expect(currentScroll).toBe(100)

    documentHeight = 2400
    // 네트워크 응답에 해당하는 DOM 변경만 일으킨다. 사용자 입력으로 복원을 취소하지 않는다.
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: '목록 불러오기' })) })

    await waitFor(() => expect(currentScroll).toBe(1024))
  })

  it('목록을 기다리던 사용자가 직접 스크롤하면 늦은 응답이 위치를 되돌리지 않는다', async () => {
    const user = userEvent.setup()
    renderRoutes({ delayed: true })
    currentScroll = 1024
    fireEvent.scroll(window)
    await user.click(screen.getByRole('link', { name: '레시피 보기' }))
    documentHeight = 700
    await user.click(screen.getByRole('button', { name: '뒤로' }))

    fireEvent.wheel(window)
    currentScroll = 50
    fireEvent.scroll(window)
    documentHeight = 2400
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: '목록 불러오기' })) })

    expect(currentScroll).toBe(50)
  })
})
