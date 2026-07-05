import pytest

from ashare_research.validation.split import DateSplit


def test_date_split_requires_ordered_non_overlapping_ranges() -> None:
    DateSplit(("20200101", "20201231"), ("20210101", "20211231"), ("20220101", "20221231")).validate()

    with pytest.raises(ValueError, match="overlapping_or_unordered_splits"):
        DateSplit(("20200101", "20211231"), ("20210101", "20211231"), ("20220101", "20221231")).validate()

    with pytest.raises(ValueError, match="empty_or_invalid_split"):
        DateSplit(("20200101", ""), ("20210101", "20211231"), ("20220101", "20221231")).validate()
