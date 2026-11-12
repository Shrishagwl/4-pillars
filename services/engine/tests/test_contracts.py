from engine.contracts import ReasonGroup, reason_group


def test_reason_groups_match_loc_codes():
    assert [reason_group(c) for c in (0, 1, 6)] == [ReasonGroup.DETACHED] * 3
    assert [reason_group(c) for c in (2, 3, 7)] == [ReasonGroup.DETECTION_TIMEOUT] * 3
    assert [reason_group(c) for c in (4, 5, 8)] == [ReasonGroup.PURGED] * 3
    assert reason_group(9) is ReasonGroup.UNKNOWN
