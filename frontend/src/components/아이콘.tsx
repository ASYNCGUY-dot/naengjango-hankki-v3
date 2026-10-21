import type { SVGProps } from 'react'

const paths = {
  home: <path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1Z" />,
  search: <><circle cx="10.5" cy="10.5" r="7" /><path d="m16 16 5 5" /></>,
  plus: <><rect x="3" y="3" width="18" height="18" rx="5" /><path d="M12 7v10M7 12h10" /></>,
  image: <><rect x="3" y="3" width="18" height="18" rx="3" /><circle cx="8" cy="8" r="1.5" /><path d="m3 17 5-5 4 4 4-6 5 7" /></>,
  user: <><circle cx="12" cy="7" r="4" /><path d="M4 21v-2a6 6 0 0 1 6-6h4a6 6 0 0 1 6 6v2Z" /></>,
  fridge: <><rect x="5" y="2" width="14" height="20" rx="2" /><path d="M5 10h14M8 5v2M8 13v3" /></>,
  'chevron-right': <path d="m9 5 7 7-7 7" />,
  'arrow-right': <path d="M4 12h16m-6-6 6 6-6 6" />,
  'arrow-left': <path d="M20 12H4m6-6-6 6 6 6" />,
  heart: <path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 0 0 0-7.8Z" />,
  book: <><path d="M12 5v16M3 3h5a4 4 0 0 1 4 2 4 4 0 0 1 4-2h5v16h-5a4 4 0 0 0-4 2 4 4 0 0 0-4-2H3Z" /></>,
  bowl: <path d="M3 11h18a9 9 0 0 1-18 0ZM8 21h8M8 3v3m4-4v4m4-3v3" />,
  close: <path d="m6 6 12 12M6 18 18 6" />,
  play: <><rect x="2" y="4" width="20" height="16" rx="4" /><path d="m10 8 6 4-6 4Z" /></>,
} as const

export type IconName = keyof typeof paths

/** 같은 굵기와 크기의 선 아이콘. 이름은 버튼/링크 쪽에서 제공한다. */
export default function Icon({ name, size = 24, ...props }: Omit<SVGProps<SVGSVGElement>, 'name'> & { name: IconName; size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false" {...props}>{paths[name]}</svg>
}
