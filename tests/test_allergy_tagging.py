"""
tag_allergy가 파생 재료를 잡는지 검증한다 (2026-08-19).

이 앱은 알레르기가 있는 재료를 추천에서 빼주겠다고 사용자에게 약속한다. 그 약속의
출발점이 이 함수라, 여기가 새면 뒤의 필터가 아무리 정확해도 소용이 없다.

실제로 그랬다. 운영 DB에서 재니 대두 알레르기를 고른 사람에게 두부가 든 레시피
153개가 하나도 안 걸러진 채 추천됐다. "두부"에 "대두"라는 글자가 없기 때문이다.
"""

import pytest

from src.agents.tagging_agent import ALLERGEN_DERIVED, tag_allergy


@pytest.mark.parametrize(
    "text,allergen",
    [
        # 원래도 잡히던 것 - 회귀 방지
        ("달걀 2개", "달걀"),
        ("우유 200ml", "우유"),
        # 파생 재료 (2026-08-19에 추가)
        ("모짜렐라치즈 100g", "우유"),
        ("무염 버터 20g", "우유"),
        ("생크림 200ml", "우유"),
        ("플레인 요거트", "우유"),
        ("밀가루 2컵", "밀"),
        ("소면 200g", "밀"),
        ("부침가루 1컵", "밀"),
        ("스파게티면", "밀"),
        ("두부 한 모", "대두"),
        ("저염간장 2큰술", "대두"),
        ("된장 1큰술", "대두"),
        ("콩나물 200g", "대두"),
        ("마요네즈 3큰술", "계란"),
        ("게살 반 컵", "게"),
        ("게맛살 2개", "게"),
    ],
)
def test_derived_ingredients_are_tagged(text, allergen):
    assert allergen in tag_allergy(text)


@pytest.mark.parametrize(
    "text,allergen",
    [
        # 과잉 차단도 해롭다. 먹을 수 있는 것을 계속 빼면 사용자가 알레르기 입력을
        # 지워버리고, 그러면 진짜 위험한 것도 안 걸러진다.
        ("쌀국수 100g", "밀"),
        ("곤약면 200g", "밀"),
        ("땅콩버터 1큰술", "우유"),
        ("땅콩가루 2큰술", "대두"),
        ("멍게살 100g", "게"),
    ],
)
def test_lookalikes_are_not_tagged(text, allergen):
    assert allergen not in tag_allergy(text)


@pytest.mark.parametrize("text", ["스파게티 200g", "바게트 1개", "얇게 썬 쇠고기", "굵게 다진 사과"])
def test_crab_is_not_tagged_from_words_that_merely_contain_the_syllable(text):
    """"게"를 그대로 문자열 포함으로 찾으면 스파게티·바게트·얇게가 전부 걸린다.

    운영 DB에서 게 태그가 붙은 42개가 전부 이런 오탐이었다. 게 알레르기가 있는 사람이
    이유 없이 파스타를 못 보게 된다.
    """
    assert "게" not in tag_allergy(text)


def test_exception_only_masks_the_lookalike_not_the_whole_recipe():
    """쌀국수와 밀가루가 같이 들어 있으면 밀은 잡혀야 한다.

    예외 처리를 "이 단어가 있으면 통째로 건너뛴다"로 만들면 이 경우가 새어나간다.
    """
    assert "밀" in tag_allergy("쌀국수 100g, 밀가루 2큰술")


def test_derived_map_only_uses_canonical_allergen_names():
    """파생어 사전의 키가 ALLERGENS에 없으면 그 태그는 아무 선택지와도 안 맞는다.

    선택지는 실제 태그에서 만들어지므로, 오타 하나면 사용자가 고를 수 없는 태그가
    조용히 생긴다.
    """
    from src.agents.tagging_agent import ALLERGENS

    assert set(ALLERGEN_DERIVED) <= set(ALLERGENS)


def test_a_recipe_with_several_sources_gets_them_all():
    # 라면(밀) + 치즈(우유)
    tags = tag_allergy("라면 1봉지, 체다치즈 한 장")
    assert {"밀", "우유"} <= set(tags)
