from datetime import timedelta

MINUTE = timedelta(minutes=1)


def union(intervals):
    merged = []
    for start, end in sorted(intervals):
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
        elif end > merged[-1][1]:
            merged[-1] = (merged[-1][0], end)
    return merged


def intersections(left, right):
    i = j = 0
    while i < len(left) and j < len(right):
        left_start, left_end = left[i]
        right_start, right_end = right[j]
        start, end = max(left_start, right_start), min(left_end, right_end)
        if start < end:
            yield start, end
        if left_end <= right_end:
            i += 1
        else:
            j += 1


def duration(intervals):
    return sum((end - start) // MINUTE for start, end in intervals)


def subtract(intervals, holes):
    """Return the parts of `intervals` not covered by `holes`, as a merged list."""
    holes = union(holes)
    remaining = []
    for start, end in union(intervals):
        cursor = start
        for hole_start, hole_end in holes:
            if hole_end <= cursor:
                continue
            if hole_start >= end:
                break
            if hole_start > cursor:
                remaining.append((cursor, min(hole_start, end)))
            cursor = max(cursor, hole_end)
            if cursor >= end:
                break
        if cursor < end:
            remaining.append((cursor, end))
    return union(remaining)
