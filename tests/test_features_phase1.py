import numpy as np
import pandas as pd

from ashare_research.factors.base_features import compute_base_features, robust_cross_sectional_standardize


def fixture() -> pd.DataFrame:
    rows = []
    for code, base in [("A", 10.0), ("B", 20.0), ("C", 30.0)]:
        for i in range(70):
            rows.append({"trade_date": f"202401{i+1:02d}", "ts_code": code, "close": base + i, "volume": 100 + i})
    return pd.DataFrame(rows)


def test_base_features_windows_and_order_invariance() -> None:
    df = fixture()
    shuffled = df.sample(frac=1, random_state=1)
    a = compute_base_features(df)
    b = compute_base_features(shuffled)
    pd.testing.assert_frame_equal(a, b)
    first = a[a["ts_code"] == "A"].reset_index(drop=True)
    assert np.isnan(first.loc[0, "RET1"])
    assert np.isnan(first.loc[4, "RET5"])
    assert np.isnan(first.loc[18, "VOL_RATIO20"])
    assert np.isnan(first.loc[58, "TREND60"])
    assert first.loc[5, "RET5"] == (15.0 / 10.0 - 1.0)


def test_future_change_does_not_change_past_features() -> None:
    df = fixture()
    base = compute_base_features(df)
    changed = df.copy()
    changed.loc[changed["trade_date"] == "20240170", "close"] *= 10
    updated = compute_base_features(changed)
    cols = ["RET1", "RET5", "VOL_RATIO20", "VOLUME_WEIGHTED_RET", "TREND60"]
    pd.testing.assert_frame_equal(
        base[base["trade_date"] < "20240170"][["trade_date", "ts_code", *cols]].reset_index(drop=True),
        updated[updated["trade_date"] < "20240170"][["trade_date", "ts_code", *cols]].reset_index(drop=True),
    )


def test_cross_sectional_standardization_per_date() -> None:
    feats = compute_base_features(fixture())
    z = robust_cross_sectional_standardize(feats, min_count=2)
    assert "RET1_Z" in z.columns
    one_day = z[z["trade_date"] == "20240121"]
    assert one_day["RET1_Z"].notna().all()

