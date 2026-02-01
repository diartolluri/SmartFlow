"""Standalone algorithms used for NEA evidence.

This module intentionally implements a small number of core algorithms "from scratch"
so they can be referenced clearly in write-ups and tested in isolation.
"""

from __future__ import annotations

from typing import Callable, Iterable, List, Sequence, TypeVar


T = TypeVar("T")


def mergesort(values: Sequence[T], *, key: Callable[[T], object] | None = None) -> List[T]:
    """Return a new list containing the values sorted using mergesort.

    Mergesort is stable and runs in $O(n\\log n)$ time.

    Args:
        values: Input sequence.
        key: Optional key function (like ``sorted(..., key=...)``).

    Returns:
        A new sorted list.
    """

    items = list(values)
    if len(items) <= 1:
        return items

    if key is None:
        return _mergesort_no_key(items)
    return _mergesort_key(items, key)


def _mergesort_no_key(items: List[T]) -> List[T]:
    if len(items) <= 1:
        return items

    mid = len(items) // 2
    left = _mergesort_no_key(items[:mid])
    right = _mergesort_no_key(items[mid:])
    return _merge_no_key(left, right)


def _merge_no_key(left: List[T], right: List[T]) -> List[T]:
    merged: List[T] = []
    i = 0
    j = 0
    while i < len(left) and j < len(right):
        # Stable: prefer left when equal.
        if left[i] <= right[j]:  # type: ignore[operator]
            merged.append(left[i])
            i += 1
        else:
            merged.append(right[j])
            j += 1

    if i < len(left):
        merged.extend(left[i:])
    if j < len(right):
        merged.extend(right[j:])
    return merged


def _mergesort_key(items: List[T], key: Callable[[T], object]) -> List[T]:
    if len(items) <= 1:
        return items

    mid = len(items) // 2
    left = _mergesort_key(items[:mid], key)
    right = _mergesort_key(items[mid:], key)
    return _merge_key(left, right, key)


def _merge_key(left: List[T], right: List[T], key: Callable[[T], object]) -> List[T]:
    merged: List[T] = []
    i = 0
    j = 0
    while i < len(left) and j < len(right):
        # Stable: prefer left when equal.
        if key(left[i]) <= key(right[j]):
            merged.append(left[i])
            i += 1
        else:
            merged.append(right[j])
            j += 1

    if i < len(left):
        merged.extend(left[i:])
    if j < len(right):
        merged.extend(right[j:])
    return merged


def histogram_peak(values: Iterable[float], *, bin_size: float) -> int:
    """Return the maximum number of values in any histogram bin.

    Used by the scenario departure-scheduling optimisation.
    """

    if bin_size <= 0:
        raise ValueError("bin_size must be > 0")

    bins: dict[int, int] = {}
    peak = 0
    for v in values:
        idx = int(float(v) // float(bin_size))
        bins[idx] = bins.get(idx, 0) + 1
        if bins[idx] > peak:
            peak = bins[idx]
    return peak
