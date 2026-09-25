"""Room shapes.

A layout is a list of seat positions in clockwise order. Positions are in
the unit square (0..1, 0..1), with y pointing down. Seat order sets who
sits next to whom, which the Chef and the Empath depend on.
"""

import math

SHAPES = ("circle", "horseshoe", "square", "grid")


def _along_path(points: list[tuple[float, float]], n: int, closed: bool) -> list[tuple[float, float]]:
    """Put n seats at equal spacing along a polyline."""
    path = points + ([points[0]] if closed else [])
    segs = [(path[i], path[i + 1]) for i in range(len(path) - 1)]
    lengths = [math.dist(a, b) for a, b in segs]
    total = sum(lengths)
    step = total / n if closed else total / max(n - 1, 1)
    out = []
    for k in range(n):
        d = k * step
        for (a, b), length in zip(segs, lengths):
            if d <= length + 1e-9:
                t = d / length if length else 0
                out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
                break
            d -= length
        else:
            out.append(path[-1])
    return out


def layout(shape: str, seats: int = 0, rows: int = 0, cols: int = 0,
           cells: list[list[int]] | None = None) -> list[dict]:
    """Return seat dicts {index, x, y} in clockwise order."""
    if shape == "circle":
        pts = [(0.5 + 0.42 * math.sin(2 * math.pi * k / seats),
                0.5 - 0.42 * math.cos(2 * math.pi * k / seats)) for k in range(seats)]
    elif shape == "horseshoe":
        # Open at the bottom: up the left side, across the top, down the right.
        pts = _along_path([(0.1, 0.92), (0.1, 0.1), (0.9, 0.1), (0.9, 0.92)], seats, closed=False)
    elif shape == "square":
        pts = _along_path([(0.1, 0.1), (0.9, 0.1), (0.9, 0.9), (0.1, 0.9)], seats, closed=True)
    elif shape == "grid":
        if not cells:
            raise ValueError("grid needs selected cells")
        pts = [((c + 0.5) / cols, (r + 0.5) / rows) for r, c in cells]
    else:
        raise ValueError(f"unknown shape {shape!r}")
    return [{"index": i, "x": round(x, 4), "y": round(y, 4)} for i, (x, y) in enumerate(pts)]
