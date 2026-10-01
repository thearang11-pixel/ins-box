import pytest

from ins_box import box, display_width


def test_box_single_line():
    assert box("hi") == "\n".join(
        [
            "┌────┐",
            "│ hi │",
            "└────┘",
        ]
    )


def test_box_multiple_lines_with_hangul():
    assert box("안녕\nhi") == "\n".join(
        [
            "┌──────┐",
            "│ 안녕 │",
            "│ hi   │",
            "└──────┘",
        ]
    )


def test_box_without_padding():
    assert box("hi", padding=0) == "\n".join(
        [
            "┌──┐",
            "│hi│",
            "└──┘",
        ]
    )


def test_box_rejects_negative_padding():
    with pytest.raises(ValueError):
        box("hi", padding=-1)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", 0),
        ("hello", 5),
        ("안녕", 4),
        ("a한b", 4),
    ],
)
def test_display_width(text, expected):
    assert display_width(text) == expected
