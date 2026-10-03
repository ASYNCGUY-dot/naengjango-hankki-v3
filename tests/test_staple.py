"""추천·영양 계산에서 빼는 기본 조미료 판정(recommendation_agent.is_staple)을 검증한다 (2026-10-02).

원래는 **부분 문자열**로 판정했다. "파"가 든 양파·파프리카·파인애플, "물"이 든 콩나물·참나물,
"마늘"이 든 마늘종이 전부 조미료로 빠졌다. 운영 레시피·냉장고 재료 이름으로 재 보니 138종 1,952회가
그랬고, 양파 하나가 922회였다. 냉장고에 양파를 넣어도 추천 겹침에 안 잡히고, 파프리카의
비타민 C가 영양 합계에서 빠졌다.

한국어 합성어는 뒤가 중심이다(저염간장은 간장, 다진마늘은 마늘). 그래서 이름이 조미료로
**끝나면** 조미료로 본다. 단 양파는 "파"로 끝나도 채소이고, 나물·해물은 "물"로 끝나도 재료다.

여기 있는 이름은 전부 운영 레시피나 냉장고에 실제로 있는 것이다.
"""

import pytest

from src.agents import recommendation_agent

is_staple = recommendation_agent.is_staple


@pytest.mark.parametrize("name", [
    "양파", "적양파", "다진양파", "양파다진것", "깐양파", "양파즙", "양파가루",
    "파프리카", "노랑 파프리카", "파프리카가루", "파인애플", "파슬리", "파슬리가루", "파스타", "스파게티",
    "파마산치즈", "아스파라거스", "베이킹파우더", "파래",
    "콩나물", "참나물", "취나물", "곤드레나물", "해물", "물오징어", "물파래", "식물성 생크림",
    "마늘종", "마늘쫑", "들기름",
])
def test_real_ingredients_that_contain_a_seasoning_word_are_not_seasonings(name):
    assert not is_staple(name), name


@pytest.mark.parametrize("name", [
    "소금", "꽃소금", "굵은소금", "함초소금", "간장", "저염간장", "진간장", "국간장",
    "설탕", "흑설탕", "마늘", "다진마늘", "다진 마늘", "통마늘",
    "파", "대파", "쪽파", "실파", "송송 썬 파", "깨", "참깨", "통깨",
    "후추", "통후추", "식초", "사과식초", "참기름", "식용유", "고춧가루", "물엿", "요리당",
    "물", "끓는 물", "쌀뜨물", "다시마국물", "녹말물",
])
def test_seasonings_and_their_variants_are_seasonings(name):
    assert is_staple(name), name


@pytest.mark.parametrize("name", [
    "소금 적당량", "소금적당량", "후추 약간", "물필요량", "설탕기호에따라",
    "마늘다진것", "파다진것", "실파송송썬것", "대파채친것", "통후추부순것",
    "소금①", "설탕②", "간장10g", "물100g", "마늘<br>", "함초소금2g",
])
def test_quantity_and_prep_leftovers_do_not_hide_a_seasoning(name):
    """원본 텍스트에서 양·손질 표현이 이름 끝에 붙어 남았다. 떼지 않으면 "소금 적당량"이 재료가 된다."""
    assert is_staple(name), name


@pytest.mark.parametrize("name, expected", [
    ("마늘가루", True), ("마늘_가루", True), ("마늘기름", True), ("마늘오일", True),
    ("마늘즙", True), ("설탕시럽", True), ("들깨가루", True),
    ("양파가루", False), ("양파즙", False), ("파슬리가루", False), ("메이플시럽", False),
])
def test_powder_oil_juice_of_a_seasoning_is_a_seasoning(name, expected):
    """"마늘가루"는 마늘로, "양파즙"은 양파로 본다. "마늘_가루"는 냉장고에 실제로 들어 있는 값이다."""
    assert is_staple(name) is expected, name


@pytest.mark.parametrize("name", ["물전분", "물녹말", "물전분 약간", "식물성기름"])
def test_prepared_seasonings_stay_seasonings(name):
    """부분 문자열 판정이 맞게 잡던 것은 그대로 둔다. 물에 푼 전분, 식용유의 다른 이름이다."""
    assert is_staple(name), name


@pytest.mark.parametrize("name, expected", [
    ("양념 다진 마늘", True), ("[양념]간장", True), ("재료 양파", False), ("(속재료) 파프리카", False),
    ("(양념) 소금", True),
])
def test_leading_section_labels_are_ignored(name, expected):
    """"(양념) 소금"이 핵심이다. 괄호 앞을 이름으로 보므로, 앞의 분류 괄호를 안 떼면 빈 이름이 된다."""
    assert is_staple(name) is expected, name


@pytest.mark.parametrize("name", ["", "   ", "[", "()"])
def test_empty_names_are_not_seasonings(name):
    assert not is_staple(name)
