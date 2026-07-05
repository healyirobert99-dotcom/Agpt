import sys

import ashare_research.factors.executor  # noqa: F401
import ashare_research.data.local_sqlite_provider  # noqa: F401


def test_phase1_modules_do_not_import_solana_runtime_modules() -> None:
    assert "execution" not in sys.modules
    assert "strategy_manager" not in sys.modules

