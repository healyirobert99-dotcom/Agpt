import numpy as np
import pandas as pd

from ashare_research.factors.base_features import BASE_FEATURES, compute_base_features, robust_cross_sectional_standardize


ORIGINAL_BASE_FEATURES = {"RET1", "RET5", "VOL_RATIO20", "VOLUME_WEIGHTED_RET", "TREND60"}
SECOND_BATCH_BASE_FEATURES = {
    "RET20",
    "RET60",
    "RET120",
    "RET_STD20",
    "RET_STD60",
    "DOWNSIDE_RET_STD20",
    "DOWNSIDE_RET_STD60",
    "AMOUNT_MA20",
    "AMOUNT_MA60",
    "TREND20",
    "TREND120",
}


def fixture(days: int = 130) -> pd.DataFrame:
    rows = []
    for code, base in [("A", 10.0), ("B", 20.0), ("C", 30.0)]:
        for i in range(days):
            rows.append({"trade_date": f"2024{i+1:04d}", "ts_code": code, "close": base + i, "volume": 100 + i, "amount": (100 + i) * (base + i)})
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
    assert ORIGINAL_BASE_FEATURES <= set(a.columns)
    assert SECOND_BATCH_BASE_FEATURES <= set(a.columns)
    assert set(BASE_FEATURES) == ORIGINAL_BASE_FEATURES | SECOND_BATCH_BASE_FEATURES
    assert len(a) == len(df)


def test_second_batch_feature_windows_and_amount_field() -> None:
    feats = compute_base_features(fixture())
    first = feats[feats["ts_code"] == "A"].reset_index(drop=True)
    assert np.isnan(first.loc[19, "RET20"])
    assert first.loc[20, "RET20"] == (30.0 / 10.0 - 1.0)
    assert np.isnan(first.loc[59, "RET60"])
    assert first.loc[60, "RET60"] == (70.0 / 10.0 - 1.0)
    assert np.isnan(first.loc[119, "RET120"])
    assert first.loc[120, "RET120"] == (130.0 / 10.0 - 1.0)
    assert np.isnan(first.loc[18, "TREND20"])
    assert first.loc[19, "TREND20"] == (29.0 / np.mean(np.arange(10.0, 30.0)) - 1.0)
    assert np.isnan(first.loc[118, "TREND120"])
    assert first.loc[119, "TREND120"] == (129.0 / np.mean(np.arange(10.0, 130.0)) - 1.0)
    assert first.loc[19, "AMOUNT_MA20"] == np.mean([(100 + i) * (10.0 + i) for i in range(20)])
    assert first.loc[59, "AMOUNT_MA60"] == np.mean([(100 + i) * (10.0 + i) for i in range(60)])


def test_amount_features_require_real_amount_field() -> None:
    with_amount = fixture()
    without_amount = with_amount.drop(columns=["amount"])
    assert "AMOUNT_MA20" in compute_base_features(with_amount).columns
    try:
        compute_base_features(without_amount)
    except ValueError as exc:
        assert "amount" in str(exc)
    else:
        raise AssertionError("compute_base_features should require the real amount field")


def test_volatility_warmup_and_downside_no_negative_returns() -> None:
    feats = compute_base_features(fixture())
    first = feats[feats["ts_code"] == "A"].reset_index(drop=True)
    assert np.isnan(first.loc[19, "RET_STD20"])
    assert first.loc[20, "RET_STD20"] > 0
    assert np.isnan(first.loc[59, "RET_STD60"])
    assert first.loc[60, "RET_STD60"] > 0
    assert np.isnan(first.loc[19, "DOWNSIDE_RET_STD20"])
    assert first.loc[20, "DOWNSIDE_RET_STD20"] == 0.0
    assert np.isnan(first.loc[59, "DOWNSIDE_RET_STD60"])
    assert first.loc[60, "DOWNSIDE_RET_STD60"] == 0.0

    negative = fixture()
    negative.loc[(negative["ts_code"] == "A") & (negative["trade_date"] == "20240011"), "close"] = 1.0
    negative_feats = compute_base_features(negative)
    negative_first = negative_feats[negative_feats["ts_code"] == "A"].reset_index(drop=True)
    assert negative_first.loc[20, "DOWNSIDE_RET_STD20"] > 0


def test_future_change_does_not_change_past_features() -> None:
    df = fixture()
    base = compute_base_features(df)
    changed = df.copy()
    changed.loc[changed["trade_date"] == "20240130", "close"] *= 10
    changed.loc[changed["trade_date"] == "20240130", "amount"] *= 10
    updated = compute_base_features(changed)
    cols = list(BASE_FEATURES)
    pd.testing.assert_frame_equal(
        base[base["trade_date"] < "20240130"][["trade_date", "ts_code", *cols]].reset_index(drop=True),
        updated[updated["trade_date"] < "20240130"][["trade_date", "ts_code", *cols]].reset_index(drop=True),
    )


def test_cross_sectional_standardization_per_date() -> None:
    feats = compute_base_features(fixture())
    z = robust_cross_sectional_standardize(feats, min_count=2)
    assert "RET1_Z" in z.columns
    one_day = z[z["trade_date"] == "20240121"]
    assert one_day["RET1_Z"].notna().all()
