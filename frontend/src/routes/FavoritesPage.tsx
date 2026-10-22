import { Link } from 'react-router-dom'
import FavoritesSection from '../components/FavoritesSection'
import Icon from '../components/아이콘'
import styles from './FavoritesPage.module.css'

export default function FavoritesPage() {
  return <div className={styles.page}>
    <Link className={styles.back} to="/my"><Icon name="arrow-left" size={18} />마이로 돌아가기</Link>
    <h1>즐겨찾기</h1>
    <FavoritesSection />
  </div>
}
