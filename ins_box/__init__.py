"""Draw a box around text, keeping Korean and other wide characters aligned."""

import unicodedata

__all__ = ["box", "display_width"]


def display_width(text):
    """Return how many terminal columns ``text`` takes up.

    East Asian wide and fullwidth characters (such as Hangul) take two
    columns; everything else takes one.
    """
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text)


def box(text, padding=1):
    """Return ``text`` surrounded by a box drawn with line characters.

    ``text`` may contain several lines separated by ``\\n``. ``padding`` is the
    number of spaces between the text and the left and right borders.
    """
    if padding < 0:
        raise ValueError("padding must be 0 or greater")

    lines = text.split("\n")
    inner = max(display_width(line) for line in lines)
    pad = " " * padding

    rows = ["┌" + "─" * (inner + 2 * padding) + "┐"]
    for line in lines:
        fill = " " * (inner - display_width(line))
        rows.append("│" + pad + line + fill + pad + "│")
    rows.append("└" + "─" * (inner + 2 * padding) + "┘")
    return "\n".join(rows)
