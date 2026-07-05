from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DateSplit:
    train: tuple[str, str]
    validation: tuple[str, str]
    blind_test: tuple[str, str]

    def validate(self) -> None:
        ranges = [self.train, self.validation, self.blind_test]
        for start, end in ranges:
            if not start or not end or start > end:
                raise ValueError("empty_or_invalid_split")
        if not (self.train[1] < self.validation[0] and self.validation[1] < self.blind_test[0]):
            raise ValueError("overlapping_or_unordered_splits")

