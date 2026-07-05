from __future__ import annotations

import numpy as np
import pandas as pd


BASE_FEATURES = (
    "RET1",
    "RET5",
    "VOL_RATIO20",
    "VOLUME_WEIGHTED_RET",
    "TREND60",
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
)


def compute_base_features(
    bars: pd.DataFrame,
    *,
    price_col: str = "close",
    volume_col: str = "volume",
    amount_col: str = "amount",
) -> pd.DataFrame:
    required = {"trade_date", "ts_code", price_col, volume_col, amount_col}
    missing = required - set(bars.columns)
    if missing:
        raise ValueError(f"Missing columns for base features: {sorted(missing)}")

    df = bars.copy()
    df["trade_date"] = df["trade_date"].astype(str)
    df = df.sort_values(["ts_code", "trade_date"], kind="mergesort")
    g = df.groupby("ts_code", sort=False, group_keys=False)
    price = df[price_col].astype(float)
    volume = df[volume_col].astype(float)
    amount = df[amount_col].astype(float)

    df["RET1"] = g[price_col].pct_change(1)
    df["RET5"] = g[price_col].pct_change(5)
    df["RET20"] = g[price_col].pct_change(20)
    df["RET60"] = g[price_col].pct_change(60)
    df["RET120"] = g[price_col].pct_change(120)
    vol_ma20 = volume.groupby(df["ts_code"], sort=False).transform(lambda s: s.rolling(20, min_periods=20).mean())
    df["VOL_RATIO20"] = volume / vol_ma20 - 1.0
    df["VOLUME_WEIGHTED_RET"] = df["RET1"] * (df["VOL_RATIO20"] + 1.0)
    df["RET_STD20"] = df["RET1"].groupby(df["ts_code"], sort=False).transform(lambda s: s.rolling(20, min_periods=20).std(ddof=0))
    df["RET_STD60"] = df["RET1"].groupby(df["ts_code"], sort=False).transform(lambda s: s.rolling(60, min_periods=60).std(ddof=0))
    downside_ret = df["RET1"].where(df["RET1"] < 0.0, 0.0).where(df["RET1"].notna())
    df["DOWNSIDE_RET_STD20"] = downside_ret.groupby(df["ts_code"], sort=False).transform(lambda s: s.rolling(20, min_periods=20).std(ddof=0))
    df["DOWNSIDE_RET_STD60"] = downside_ret.groupby(df["ts_code"], sort=False).transform(lambda s: s.rolling(60, min_periods=60).std(ddof=0))
    df["AMOUNT_MA20"] = amount.groupby(df["ts_code"], sort=False).transform(lambda s: s.rolling(20, min_periods=20).mean())
    df["AMOUNT_MA60"] = amount.groupby(df["ts_code"], sort=False).transform(lambda s: s.rolling(60, min_periods=60).mean())
    ma20 = price.groupby(df["ts_code"], sort=False).transform(lambda s: s.rolling(20, min_periods=20).mean())
    ma60 = price.groupby(df["ts_code"], sort=False).transform(lambda s: s.rolling(60, min_periods=60).mean())
    ma120 = price.groupby(df["ts_code"], sort=False).transform(lambda s: s.rolling(120, min_periods=120).mean())
    df["TREND20"] = price / ma20 - 1.0
    df["TREND60"] = price / ma60 - 1.0
    df["TREND120"] = price / ma120 - 1.0

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
