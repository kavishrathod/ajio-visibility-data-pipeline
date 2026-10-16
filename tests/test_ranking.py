from src.pipeline.ranking import RankState, assign_ranks


def test_rank_order_and_relative_rank():
    ranks, _ = assign_ranks(["SB", "SP", "Organic", "Organic", "SP", "Organic"])
    assert ranks == [(1, 1), (2, 1), (3, 1), (4, 2), (5, 2), (6, 3)]


def test_ranks_continue_across_pages():
    _, state = assign_ranks(["SB", "SP"] + ["Organic"] * 38)
    ranks, next_state = assign_ranks(["Organic", "SP"], state)
    assert ranks == [(41, 39), (42, 2)]
    assert next_state.absolute == 42


def test_empty_sequence_does_not_change_state():
    state = RankState(absolute=4, per_type={"SP": 2})
    ranks, next_state = assign_ranks([], state)
    assert ranks == []
    assert next_state == state
