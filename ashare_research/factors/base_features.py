from __future__ import annotations

import numpy as np
import pandas as pd


BASE_FEATURES = ("RET1", "RET5", "VOL_RATIO20", "VOLUME_WEIGHTED_RET", "TREND60")


def compute_base_features(
    bars: pd.DataFrame,
    *,
    price_col: str = "close",
    volume_col: str = "volume",
) -> pd.DataFrame:
    required = {"trade_date", "ts_code", price_col, volume_col}
    missing = required - set(bars.columns)
    if missing:
        raise ValueError(f"Missing columns for base features: {sorted(missing)}")

    df = bars.copy()
    df["trade_date"] = df["trade_date"].astype(str)
    df = df.sort_values(["ts_code", "trade_date"], kind="mergesort")
    g = df.groupby("ts_code", sort=False, group_keys=False)
    price = df[price_col].astype(float)
    volume = df[volume_col].astype(float)

    df["RET1"] = g[price_col].pct_change(1)
    df["RET5"] = g[price_col].pct_change(5)
    vol_ma20 = volume.groupby(df["ts_code"], sort=False).transform(lambda s: s.rolling(20, min_periods=20).mean())
    df["VOL_RATIO20"] = volume / vol_ma20 - 1.0
    df["VOLUME_WEIGHTED_RET"] = df["RET1"] * (df["VOL_RATIO20"] + 1.0)
    ma60 = price.groupby(df["ts_code"], sort=False).transform(lambda s: s.rolling(60, min_periods=60).mean())
    df["TREND60"] = price / ma60 - 1.0

    cols = ["trade_date", "ts_code", *BASE_FEATURES]
    return df[cols].sort_values(["trade_date", "ts_code"], kind="mergesort").reset_index(drop=True)


def robust_cross_sectional_standardize(
    features: pd.DataFrame,
    *,
    feature_cols: tuple[str, ...] = BASE_FEATURES,
    min_count: int = 10,
) -> pd.DataFrame:
    required = {"trade_date", "ts_code", *feature_cols}
    missing = required - set(features.columns)
    if missing:
        raise ValueError(f"Missing columns for standardization: {sorted(missing)}")

    out = features[["trade_date", "ts_code"]].copy()
    failure_reasons: list[pd.Series] = []
    for col in feature_cols:
        def _std(s: pd.Series) -> pd.Series:
            valid = s.dropna()
            if len(valid) < min_count:
                return pd.Series(np.nan, index=s.index)
            med = valid.median()
            mad = (valid - med).abs().median()
            if not np.isfinite(mad) or mad == 0:
                return pd.Series(np.nan, index=s.index)
            return ((s - med) / (1.4826 * mad)).clip(-5, 5)

        out[f"{col}_Z"] = features.groupby("trade_date", sort=False)[col].transform(_std)
    return out

