import { Link } from 'react-router-dom'

import Icon from '../components/아이콘'
import HomeFeed from '../components/집밥피드'
import styles from './BragPage.module.css'

export default function BragPage() {
  return (
    <div className={styles.page}>
      <header className={styles.head}>
        <div>
          <h1>자랑하기</h1>
          <p>오늘의 집밥을 나눠요</p>
        </div>
        <Link className={styles.write} to="/brags/new">
          <Icon name="plus" size={18} />
          글쓰기
        </Link>
      </header>
      <HomeFeed />
    </div>
  )
}
