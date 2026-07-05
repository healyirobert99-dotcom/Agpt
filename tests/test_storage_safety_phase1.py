from pathlib import Path

import pytest

from ashare_research.data.store import ensure_free_space


def test_disk_threshold_check_passes_for_tiny_requirement() -> None:
    ensure_free_space(Path("."), 1)


def test_disk_threshold_check_fails_for_impossible_requirement() -> None:
    with pytest.raises(RuntimeError):
        ensure_free_space(Path("."), 10**30)
