"""가입·온보딩 선택지가 서버가 아는 값과 일치하는지 검증한다 (2026-08-18).

왜 만들었나
화면이 선택지를 따로 들고 있어서 서버가 아는 값과 조용히 어긋나 있었다.

  가입 화면:  10대 20대 30대 40대 50대 60대이상
  RDA 표:     10대 20대 30대 40대 50대이상

"50대"나 "60대 이상"을 고른 사람은 영양 기준을 하나도 못 받는데, 화면은 저장됐다고
말한다. 병력 정보도 자유 입력이라 "혈압 높음"이라고 쓰면 고혈압 나트륨 조정이 안 걸렸다.

알레르기에서 이미 겪은 구조라 같은 방식으로 막는다 - 서버가 목록을 내려주고 화면은
거기서만 고른다.
"""

from src.agents import nutrition_target_agent


def _options(client):
    res = client.get("/profile/options")
    assert res.status_code == 200, res.text
    return res.json()


def test_options_are_public(client):
    # 가입 전에도 필요하다. 인가를 걸면 회원가입 화면이 선택지를 못 받는다.
    assert client.get("/profile/options").status_code == 200


def test_every_age_group_has_a_nutrition_target(client):
    """이게 이 파일에서 가장 중요한 검사다. 고를 수 있는데 기준이 없으면 안 된다."""
    for age_group in _options(client)["age_groups"]:
        for gender in nutrition_target_agent.GENDERS_WITH_TARGETS:
            assert (gender, age_group) in nutrition_target_agent.RDA_TABLE, (
                f"{gender}/{age_group}를 고를 수 있는데 RDA 표에 기준이 없다"
            )


def test_every_age_group_has_a_bracket_label(client):
    for age_group in _options(client)["age_groups"]:
        assert age_group in nutrition_target_agent.AGE_GROUP_TO_BRACKET_LABEL


def test_undisclosed_gender_is_offered_but_has_no_target(client):
    # 건강 정보를 강제로 받지 않는다. 대신 그때는 영양 기준을 못 준다고 화면이 알아야 한다.
    options = _options(client)
    assert options["gender_undisclosed"] in options["genders"]
    assert options["gender_undisclosed"] not in nutrition_target_agent.GENDERS_WITH_TARGETS


def test_medical_conditions_match_what_the_parser_accepts(client):
    """목록에 없는 값은 parse_conditions가 조용히 버린다. 화면이 그 목록을 그대로 써야 한다."""
    offered = _options(client)["medical_conditions"]
    parsed = nutrition_target_agent.parse_conditions(",".join(offered))
    assert parsed == set(offered)


def test_a_free_text_condition_is_silently_dropped():
    """왜 목록이어야 하는지의 근거. 자유 입력은 조용히 버려진다."""
    assert nutrition_target_agent.parse_conditions("혈압 높음") == set()
    assert nutrition_target_agent.parse_conditions("고혈압") == {"고혈압"}
