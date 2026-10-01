from ins_box import box


def test_box_single_line():
    assert box("hi") == "\n".join(
        [
            "┌────┐",
            "│ hi │",
            "└────┘",
        ]
    )
