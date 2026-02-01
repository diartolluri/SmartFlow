from __future__ import annotations

import random

from smartflow.core.algorithms import mergesort


def test_mergesort_matches_builtin_sorted() -> None:
    rng = random.Random(123)
    values = [rng.uniform(-100, 100) for _ in range(500)]
    assert mergesort(values) == sorted(values)


def test_mergesort_stable_for_equal_keys() -> None:
    # (value, original_index) pairs, sort by value only.
    items = [(1, "a"), (1, "b"), (0, "c"), (1, "d"), (0, "e")]
    sorted_items = mergesort(items, key=lambda x: x[0])

    # Within each value bucket, relative order should be preserved.
    ones = [x[1] for x in sorted_items if x[0] == 1]
    zeros = [x[1] for x in sorted_items if x[0] == 0]
    assert zeros == ["c", "e"]
    assert ones == ["a", "b", "d"]
