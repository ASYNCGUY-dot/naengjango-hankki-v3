import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from '../App'
import { renderWithProviders } from '../test/renderWithProviders'

describe('약관·개인정보 문서', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.restoreAllMocks())

  it('동의 체크박스에서 실제 문서로 갈 수 있다', () => {
    // 문서 없이 동의만 받으면 그 동의는 기록으로서 의미가 없다. 실제로 그 상태였다
    // (2026-08-18) - 체크박스는 라벨뿐이고 링크도 문서도 없었다.
    renderWithProviders(<App />, { route: '/signup' })

    const links = screen.getAllByRole('link', { name: '보기' })
    expect(links.map((link) => link.getAttribute('href'))).toEqual(['/terms', '/privacy'])
  })

  it('문서 링크를 눌러도 동의가 켜지지 않는다', async () => {
    // 라벨 안에 링크를 넣으면 링크를 누를 때 체크박스가 함께 토글된다. 문서를 보려던
    // 사람이 동의를 켜버리는 셈이라, 동의로 볼 수 없다.
    const user = userEvent.setup()
    renderWithProviders(<App />, { route: '/signup' })

    await user.click(screen.getAllByRole('link', { name: '보기' })[0])

    expect(screen.getByLabelText('(필수) 이용약관에 동의합니다')).not.toBeChecked()
  })

  it('개인정보 안내가 알레르기와 병력을 빠뜨리지 않는다', () => {
    // 가입 화면의 안내는 "아이디, 이름, 연락처, 이메일, 성별, 연령대"만 적고 있었다.
    // 온보딩에서 받는 건강 정보가 빠져 있었는데, 그게 가장 민감한 항목이다.
    renderWithProviders(<App />, { route: '/privacy' })

    const main = screen.getByRole('main')
    expect(main).toHaveTextContent('알레르기')
    expect(main).toHaveTextContent('병력 정보')
    expect(main).toHaveTextContent('건강에 관한 정보')
  })

  it('없는 기능을 약속하지 않는다', () => {
    // 원래 문구는 "회원 탈퇴 시 지웁니다"였는데 탈퇴 기능이 없다. 지금은 사람이 직접
    // 지운다고 사실대로 적는다.
    renderWithProviders(<App />, { route: '/privacy' })

    const main = screen.getByRole('main')
    expect(main).toHaveTextContent('만든 사람에게 말씀해주시면 지웁니다')
    expect(main).not.toHaveTextContent('탈퇴 버튼을 누르면')
  })

  it('알레르기 제외가 완전하지 않다는 것을 약관에서 밝힌다', () => {
    // 태그가 빠진 레시피는 걸러지지 않는다. 알레르기가 심한 사람에게는 안전 문제라
    // 기능 설명이 아니라 경고로 적어야 한다.
    renderWithProviders(<App />, { route: '/terms' })

    const main = screen.getByRole('main')
    expect(main).toHaveTextContent('완전하지 않습니다')
    expect(main).toHaveTextContent('재료를 직접 확인하세요')
  })

  it('두 문서가 서로 오갈 수 있다', () => {
    renderWithProviders(<App />, { route: '/terms' })
    expect(screen.getByRole('link', { name: '개인정보 수집·이용 안내 보기' })).toHaveAttribute(
      'href',
      '/privacy',
    )
  })
})
