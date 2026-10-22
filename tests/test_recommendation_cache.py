"""추천의 반복 계산을 줄이되 순위·점수·새 데이터는 그대로여야 한다."""

from copy import deepcopy

import pytest

from src.agents import recommendation_agent as agent


@pytest.mark.parametrize("name", [
    "_is_protein", "_clean_ingredient_name", "_classify_ingredient_name",
])
def test_repeated_names_use_a_bounded_cache(name):
    fn = getattr(agent, name, None)
    assert fn is not None and hasattr(fn, "cache_info"), "반복 계산용 캐시가 없다"
    fn.cache_clear()
    try:
        first = fn("[주재료]닭가슴살")
        assert fn("[주재료]닭가슴살") == first
        assert fn.cache_info().misses == 1
        assert fn.cache_info().hits == 1
        assert 0 < fn.cache_info().maxsize <= 8192
    finally:
        fn.cache_clear()


@pytest.mark.parametrize("ingredients", [
    [], ["두부"], ["양파"], ["닭가슴살", "양파"],
    ["고등어", "갈치", "참치", "전지", "소금"],
    ["달걀", "계란", "양배추"], ["주재료", "1인분기준<br>", ""],
])
def test_cold_and_warm_recommendations_equal_uncached_results(db_conn, monkeypatch, ingredients):
    candidates = agent.get_candidate_recipes(db_conn.cursor(), {})
    cached_functions = {}
    for name in ("_is_protein", "_clean_ingredient_name", "_classify_ingredient_name"):
        fn = getattr(agent, name, None)
        assert fn is not None and hasattr(fn, "__wrapped__"), "캐시 적용 전"
        fn.cache_clear()
        cached_functions[name] = fn
    with monkeypatch.context() as patch:
        for name, fn in cached_functions.items():
            patch.setattr(agent, name, fn.__wrapped__)
        expected = agent.score_by_ingredients(db_conn.cursor(), deepcopy(candidates), ingredients)
    try:
        assert agent.score_by_ingredients(db_conn.cursor(), deepcopy(candidates), ingredients) == expected
        assert agent.score_by_ingredients(db_conn.cursor(), deepcopy(candidates), ingredients) == expected
    finally:
        for fn in cached_functions.values():
            fn.cache_clear()


def test_warm_cache_does_not_hide_new_recipe_rows_or_mix_user_inputs(db_conn):
    candidates = agent.get_candidate_recipes(db_conn.cursor(), {})

    def score(names):
        return next(row for row in agent.score_by_ingredients(
            db_conn.cursor(), deepcopy(candidates), names,
        ) if row["id"] == 1)

    tofu = score(["두부"])
    assert tofu["ingredient_overlap"] == 1
    assert tofu["has_protein_match"] is False
    assert score(["고등어"])["ingredient_overlap"] == 0
    db_conn.execute(
        "INSERT INTO recipe_tags (recipe_id, tag_type, tag_value) VALUES (1, 'ingredient', '고등어')",
    )
    changed = score(["고등어"])
    assert changed["ingredient_overlap"] == 1
    assert changed["has_protein_match"] is True
    assert score(["두부"])["has_protein_match"] is False


@pytest.mark.parametrize("name,kind", [
    ("양파", "ingredient"), ("주재료", "section"),
    ("[주재료]닭가슴살", "ingredient"), ("1인분기준<br>", "noise"), ("", "noise"),
])
def test_name_classification_keeps_existing_section_and_noise_rules(name, kind):
    assert agent._classify_ingredient_name(name) == kind


def test_shared_classification_still_uses_amount():
    assert agent.portion_agent.classify_ingredient_row("주재료", None) == "section"
    assert agent.portion_agent.classify_ingredient_row("주재료", 10) == "ingredient"


def test_scoring_actually_reuses_all_three_name_caches(db_conn):
    functions = [agent._is_protein, agent._clean_ingredient_name, agent._classify_ingredient_name]
    for fn in functions:
        fn.cache_clear()
    try:
        candidates = agent.get_candidate_recipes(db_conn.cursor(), {})
        agent.score_by_ingredients(db_conn.cursor(), deepcopy(candidates), ["두부", "닭가슴살"])
        first = [fn.cache_info() for fn in functions]
        agent.score_by_ingredients(db_conn.cursor(), deepcopy(candidates), ["두부", "닭가슴살"])
        for fn, initial in zip(functions, first):
            assert initial.misses > 0
            assert fn.cache_info().misses == initial.misses
            assert fn.cache_info().hits > initial.hits
    finally:
        for fn in functions:
            fn.cache_clear()
