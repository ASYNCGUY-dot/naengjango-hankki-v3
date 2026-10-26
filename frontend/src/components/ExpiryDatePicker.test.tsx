import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import ExpiryDatePicker from './ExpiryDatePicker'

// 실제 브라우저의 dialog 동작 중 테스트에 필요한 open 상태만 재현한다.
if (!HTMLDialogElement.prototype.showModal) {
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', {
    configurable: true,
    value(this: HTMLDialogElement) { this.open = true },
  })
}
if (!HTMLDialogElement.prototype.close) {
  Object.defineProperty(HTMLDialogElement.prototype, 'close', {
    configurable: true,
    value(this: HTMLDialogElement) {
      this.open = false
      this.dispatchEvent(new Event('close'))
    },
  })
}

describe('소비기한 휠 선택', () => {
  it('연도·월·일을 눌러 바꿔도 완료하기 전에는 저장하지 않는다', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<ExpiryDatePicker value="2026-10-22" onChange={onChange} />)
    const trigger = screen.getByRole('button', { name: '소비기한' })
    expect(trigger).toHaveTextContent('2026-10-22')

    await user.click(trigger)
    await user.click(screen.getByRole('button', { name: '2027년' }))
    await user.click(screen.getByRole('button', { name: '11월' }))
    await user.click(screen.getByRole('button', { name: '23일' }))
    expect(onChange).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: '선택 완료' }))

    expect(onChange).toHaveBeenCalledExactlyOnceWith('2027-11-23')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
  })

  it.each(['취소', 'Escape'])('%s로 닫으면 수정한 날짜를 버리고 기존 날짜로 다시 연다', async (method) => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<ExpiryDatePicker value="2026-10-22" onChange={onChange} />)
    const trigger = screen.getByRole('button', { name: '소비기한' })
    await user.click(trigger)
    await user.click(screen.getByRole('button', { name: '2027년' }))

    if (method === '취소') {
      await user.click(screen.getByRole('button', { name: '취소' }))
    } else {
      // 브라우저는 모달에서 Escape를 누르면 cancel 이벤트를 보낸다.
      fireEvent(screen.getByRole('dialog'), new Event('cancel', { cancelable: true }))
    }

    expect(onChange).not.toHaveBeenCalled()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
    await user.click(trigger)
    expect(screen.getByRole('spinbutton', { name: '연도' })).toHaveAttribute('aria-valuenow', '2026')
  })

  it('날짜 지우기를 누르면 소비기한을 없앤다', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<ExpiryDatePicker value="2026-10-22" onChange={onChange} />)
    await user.click(screen.getByRole('button', { name: '소비기한' }))
    await user.click(screen.getByRole('button', { name: '날짜 지우기' }))

    expect(onChange).toHaveBeenCalledExactlyOnceWith('')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('31일에서 2월로 이동하거나 윤년을 바꾸면 존재하는 마지막 날로 맞춘다', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<ExpiryDatePicker value="2028-01-31" onChange={onChange} />)
    await user.click(screen.getByRole('button', { name: '소비기한' }))
    await user.click(screen.getByRole('button', { name: '2월' }))
    expect(screen.getByRole('spinbutton', { name: '일' })).toHaveAttribute('aria-valuenow', '29')

    await user.click(screen.getByRole('spinbutton', { name: '연도' }))
    await user.keyboard('{ArrowDown}')
    expect(screen.getByRole('spinbutton', { name: '연도' })).toHaveAttribute('aria-valuenow', '2027')
    expect(screen.getByRole('spinbutton', { name: '일' })).toHaveAttribute('aria-valuenow', '28')
    await user.click(screen.getByRole('button', { name: '선택 완료' }))
    expect(onChange).toHaveBeenCalledExactlyOnceWith('2027-02-28')
  })

  it('키보드로 월을 고를 때 1월과 12월의 경계를 넘지 않는다', async () => {
    const user = userEvent.setup()
    render(<ExpiryDatePicker value="2026-10-22" onChange={vi.fn()} />)
    await user.click(screen.getByRole('button', { name: '소비기한' }))
    const month = screen.getByRole('spinbutton', { name: '월' })
    await user.click(month)
    await user.keyboard('{Home}{ArrowDown}')
    expect(month).toHaveAttribute('aria-valuenow', '1')
    await user.keyboard('{End}{ArrowUp}')
    expect(month).toHaveAttribute('aria-valuenow', '12')
  })

  it('각 휠을 스크롤하면 가운데 날짜가 바뀌고 확정한 값을 저장한다', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<ExpiryDatePicker value="2027-10-22" onChange={onChange} />)
    await user.click(screen.getByRole('button', { name: '소비기한' }))
    const year = screen.getByRole('spinbutton', { name: '연도' })
    const month = screen.getByRole('spinbutton', { name: '월' })
    const day = screen.getByRole('spinbutton', { name: '일' })
    // 처음 10월이 중앙에 놓인 스크롤 위치에서 한 행의 간격을 구한다.
    const rowHeight = month.scrollTop / 9
    expect(rowHeight).toBeGreaterThan(0)

    fireEvent.scroll(year, { target: { scrollTop: year.scrollTop + rowHeight } })
    fireEvent.scroll(month, { target: { scrollTop: rowHeight } })
    fireEvent.scroll(day, { target: { scrollTop: rowHeight * 28 } })

    expect(year).toHaveAttribute('aria-valuenow', '2028')
    expect(month).toHaveAttribute('aria-valuenow', '2')
    expect(day).toHaveAttribute('aria-valuenow', '29')
    expect(onChange).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: '선택 완료' }))
    expect(onChange).toHaveBeenCalledExactlyOnceWith('2028-02-29')
  })
})
