from ahk_workspace_manager.ui import optional_group_name


def test_cancelled_group_prompt_returns_no_group():
    assert optional_group_name(None, False) is None


def test_blank_group_prompt_returns_no_group():
    assert optional_group_name("   ", True) is None


def test_group_prompt_trims_name():
    assert optional_group_name(" thumb_buttons ", True) == "thumb_buttons"

