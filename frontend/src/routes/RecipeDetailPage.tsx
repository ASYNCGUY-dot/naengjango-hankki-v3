import { useParams } from 'react-router-dom'

/**
 * V2에서는 이 화면이 URL을 갖지 못해 링크로 공유할 수 없었다. 여기서 recipeId를
 * 주소에서 읽는다는 것 자체가 React 전환의 실질 이득이다.
 */
export default function RecipeDetailPage() {
  const { recipeId } = useParams<{ recipeId: string }>()

  return (
    <section>
      <h1>레시피 상세</h1>
      <p>recipeId: {recipeId}</p>
    </section>
  )
}
