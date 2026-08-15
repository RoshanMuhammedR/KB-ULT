"""Turn a chunk's character range into the regions a viewer can highlight.

A chunk is a slice of one segment's text. A segment also carries the geometry it was built
from — `spans` for paged sources (one text block, with a rect), `region` for timed ones (the
window's start and end). This module maps the slice back onto that geometry.

Pure functions over plain dicts: no PyMuPDF, no database, no I/O. That is deliberate, because
the alignment logic is the part most likely to be wrong and the part cheapest to reason about
in isolation.
"""

from __future__ import annotations

# Beyond this many rectangles a highlight stops reading as "here is the passage" and starts
# reading as visual noise, so the region collapses to one box covering all of them instead.
MAX_RECTS_PER_PAGE = 32

# Two rects are merged when they sit within this fraction of the page height of each other and
# overlap horizontally — consecutive lines of one paragraph, in other words. Keeps a 12-line
# quote from emitting 12 separate boxes.
_VERTICAL_MERGE_GAP = 0.012


def resolve_paged_regions(
    spans: list[dict] | None,
    char_start: int,
    char_end: int,
    segment_text: str,
) -> list[dict]:
    """Select the spans a chunk overlaps and group their rects by page.

    Spans carry text but not their own offsets into the segment: the segment string is the
    parser's markdown, while spans come from PyMuPDF's block extraction, so the two are
    similar but not character-identical. Rather than trust a fragile reconstruction, each
    span is located in the segment text by search, and spans that cannot be found are skipped
    — a missing highlight is a far better failure than a wrong one.
    """
    if not spans:
        return []

    by_page: dict[int, list[list[float]]] = {}
    cursor = 0
    for span in spans:
        text = (span.get("text") or "").strip()
        rect = span.get("rect")
        if not text or not rect:
            continue

        # Search forward from the last match so repeated text (a running header, a table cell)
        # maps to successive occurrences rather than all colliding on the first one.
        found = segment_text.find(text, cursor)
        if found < 0:
            found = segment_text.find(text)
            if found < 0:
                continue
        else:
            cursor = found + len(text)

        # Half-open overlap test: the span must share at least one character with the chunk.
        if found >= char_end or found + len(text) <= char_start:
            continue

        page = span.get("page")
        if page is None:
            continue
        by_page.setdefault(int(page), []).append([float(value) for value in rect])

    regions = []
    for page in sorted(by_page):
        regions.append({"page": page, "rects": _compact(by_page[page])})
    return regions


def _compact(rects: list[list[float]]) -> list[list[float]]:
    """Merge vertically adjacent, horizontally overlapping rects; cap the result."""
    if not rects:
        return []

    ordered = sorted(rects, key=lambda rect: (rect[1], rect[0]))
    merged: list[list[float]] = [list(ordered[0])]
    for rect in ordered[1:]:
        previous = merged[-1]
        touching = rect[1] - previous[3] <= _VERTICAL_MERGE_GAP
        overlapping = rect[0] < previous[2] and previous[0] < rect[2]
        if touching and overlapping:
            previous[0] = min(previous[0], rect[0])
            previous[1] = min(previous[1], rect[1])
            previous[2] = max(previous[2], rect[2])
            previous[3] = max(previous[3], rect[3])
        else:
            merged.append(list(rect))

    if len(merged) > MAX_RECTS_PER_PAGE:
        # Too fragmented to read as a highlight — one box round the whole lot is honest about
        # the granularity actually available.
        return [
            [
                min(rect[0] for rect in merged),
                min(rect[1] for rect in merged),
                max(rect[2] for rect in merged),
                max(rect[3] for rect in merged),
            ]
        ]
    return [[round(value, 5) for value in rect] for rect in merged]


def resolve_timeline_region(
    region: dict | None,
    char_start: int,
    char_end: int,
    segment_length: int,
) -> list[dict]:
    """Narrow a segment's time window to the slice of it this chunk covers.

    Transcript lines are coalesced into ~500-character windows before splitting, so one window
    can become several chunks that would otherwise all claim the window's full duration. There
    are no per-character timings to consult, so the window is interpolated by character
    position: speech rate is roughly constant within a few hundred characters, which makes
    this a good approximation and a much better one than giving every chunk the same span.
    """
    if not region or segment_length <= 0:
        return []

    start = float(region.get("start", 0.0) or 0.0)
    end = float(region.get("end", 0.0) or 0.0)
    if end <= start:
        return []

    span = end - start
    fraction_start = max(0.0, min(1.0, char_start / segment_length))
    fraction_end = max(0.0, min(1.0, char_end / segment_length))
    if fraction_end <= fraction_start:
        return [{"start": round(start, 2), "end": round(end, 2)}]

    return [
        {
            "start": round(start + span * fraction_start, 2),
            "end": round(start + span * fraction_end, 2),
        }
    ]
