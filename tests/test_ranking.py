from ajio_pipeline.ranking import assign_ranks, RankState


def test_worked_example_from_brief():
    types = ["SB", "SP", "Organic", "Organic", "SP", "Organic"]
    ranks, _ = assign_ranks(types)
    assert ranks == [(1, 1), (2, 1), (3, 1), (4, 2), (5, 2), (6, 3)]


def test_ranks_continue_across_pages():
    # page 1: 40 units, 34 organic (6 paid)
    page1 = ["SB", "SP", "SP", "SP", "SP", "SP"] + ["Organic"] * 34
    _, state = assign_ranks(page1)
    assert state.absolute == 40
    ranks, _ = assign_ranks(["Organic"], state)
    assert ranks == [(41, 35)]
