"""Statistical utilities for a randomized three-arm cashback experiment."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats


@dataclass(frozen=True)
class ContrastResult:
    estimate: float
    standard_error: float
    ci_low: float
    ci_high: float
    p_value: float
    relative_effect: float
    effect_size: float


def standardized_mean_difference(a: pd.Series, b: pd.Series) -> float:
    """Return the pooled-standard-deviation difference in means."""
    x = pd.to_numeric(a, errors="coerce").dropna().to_numpy(dtype=float)
    y = pd.to_numeric(b, errors="coerce").dropna().to_numpy(dtype=float)
    if len(x) < 2 or len(y) < 2:
        return np.nan
    pooled = np.sqrt((np.var(x, ddof=1) + np.var(y, ddof=1)) / 2)
    return 0.0 if pooled == 0 else float((np.mean(x) - np.mean(y)) / pooled)


def continuous_contrast(
    treatment: pd.Series,
    reference: pd.Series,
    alpha: float = 0.05,
) -> ContrastResult:
    """Welch difference in means with confidence interval and Cohen's d."""
    x = pd.to_numeric(treatment, errors="coerce").dropna().to_numpy(dtype=float)
    y = pd.to_numeric(reference, errors="coerce").dropna().to_numpy(dtype=float)
    nx, ny = len(x), len(y)
    mx, my = np.mean(x), np.mean(y)
    vx, vy = np.var(x, ddof=1), np.var(y, ddof=1)
    se = np.sqrt(vx / nx + vy / ny)
    numerator = (vx / nx + vy / ny) ** 2
    denominator = ((vx / nx) ** 2 / (nx - 1)) + ((vy / ny) ** 2 / (ny - 1))
    dof = numerator / denominator if denominator else np.inf
    crit = stats.t.ppf(1 - alpha / 2, dof)
    estimate = mx - my
    p_value = 2 * stats.t.sf(abs(estimate / se), dof) if se else 1.0
    pooled = np.sqrt(((nx - 1) * vx + (ny - 1) * vy) / (nx + ny - 2))
    effect_size = estimate / pooled if pooled else 0.0
    return ContrastResult(
        estimate=float(estimate),
        standard_error=float(se),
        ci_low=float(estimate - crit * se),
        ci_high=float(estimate + crit * se),
        p_value=float(p_value),
        relative_effect=float(estimate / my) if my else np.nan,
        effect_size=float(effect_size),
    )


def binary_contrast(
    treatment: pd.Series,
    reference: pd.Series,
    alpha: float = 0.05,
) -> ContrastResult:
    """Risk difference with an unpooled Wald interval and Cohen's h."""
    x = pd.to_numeric(treatment, errors="coerce").dropna().to_numpy(dtype=float)
    y = pd.to_numeric(reference, errors="coerce").dropna().to_numpy(dtype=float)
    px, py = np.mean(x), np.mean(y)
    se = np.sqrt(px * (1 - px) / len(x) + py * (1 - py) / len(y))
    estimate = px - py
    crit = stats.norm.ppf(1 - alpha / 2)
    p_value = 2 * stats.norm.sf(abs(estimate / se)) if se else 1.0
    effect_size = 2 * (np.arcsin(np.sqrt(px)) - np.arcsin(np.sqrt(py)))
    return ContrastResult(
        estimate=float(estimate),
        standard_error=float(se),
        ci_low=float(estimate - crit * se),
        ci_high=float(estimate + crit * se),
        p_value=float(p_value),
        relative_effect=float(estimate / py) if py else np.nan,
        effect_size=float(effect_size),
    )


def holm_adjust(p_values: list[float] | np.ndarray) -> np.ndarray:
    """Holm family-wise-error adjustment, returned in original order."""
    p = np.asarray(p_values, dtype=float)
    order = np.argsort(p)
    adjusted_sorted = np.maximum.accumulate((len(p) - np.arange(len(p))) * p[order])
    adjusted_sorted = np.minimum(adjusted_sorted, 1.0)
    adjusted = np.empty_like(adjusted_sorted)
    adjusted[order] = adjusted_sorted
    return adjusted


def cuped_adjust(
    outcome: pd.Series,
    covariate: pd.Series,
    theta_sample: pd.Series | np.ndarray | None = None,
    theta_covariate: pd.Series | np.ndarray | None = None,
) -> tuple[pd.Series, float, float]:
    """Apply CUPED using a pre-treatment covariate and return variance reduction."""
    y = pd.to_numeric(outcome, errors="coerce")
    x = pd.to_numeric(covariate, errors="coerce")
    fit_y = y if theta_sample is None else pd.Series(theta_sample)
    fit_x = x if theta_covariate is None else pd.Series(theta_covariate)
    valid_fit = fit_y.notna() & fit_x.notna()
    covariance = np.cov(fit_y[valid_fit], fit_x[valid_fit], ddof=1)[0, 1]
    variance = np.var(fit_x[valid_fit], ddof=1)
    theta = float(covariance / variance) if variance else 0.0
    center = float(x.mean())
    adjusted = y - theta * (x - center)
    valid = y.notna() & adjusted.notna()
    variance_reduction = 1 - np.var(adjusted[valid], ddof=1) / np.var(y[valid], ddof=1)
    return adjusted, theta, float(variance_reduction)


def approximate_binary_mde(
    baseline_rate: float,
    n_treatment: int,
    n_control: int,
    alpha: float = 0.05,
    power: float = 0.80,
) -> float:
    """Approximate absolute MDE for a two-sided difference in proportions."""
    z_alpha = stats.norm.ppf(1 - alpha / 2)
    z_power = stats.norm.ppf(power)
    se = np.sqrt(baseline_rate * (1 - baseline_rate) * (1 / n_treatment + 1 / n_control))
    return float((z_alpha + z_power) * se)


def approximate_continuous_mde(
    pooled_sd: float,
    n_treatment: int,
    n_control: int,
    alpha: float = 0.05,
    power: float = 0.80,
) -> float:
    """Approximate absolute MDE for a two-sided difference in means."""
    z_alpha = stats.norm.ppf(1 - alpha / 2)
    z_power = stats.norm.ppf(power)
    return float((z_alpha + z_power) * pooled_sd * np.sqrt(1 / n_treatment + 1 / n_control))


def approximate_observed_power(
    effect: float,
    standard_error: float,
    alpha: float = 0.05,
) -> float:
    """Normal-approximation diagnostic power for an observed effect."""
    if standard_error <= 0:
        return 1.0
    noncentrality = abs(effect) / standard_error
    critical = stats.norm.ppf(1 - alpha / 2)
    return float(stats.norm.cdf(-critical - noncentrality) + 1 - stats.norm.cdf(critical - noncentrality))


def bayesian_bootstrap_difference(
    treatment: pd.Series,
    reference: pd.Series,
    reps: int = 500,
    seed: int = 20260927,
    chunk_size: int = 25,
) -> tuple[float, float, float]:
    """Bayesian bootstrap interval for a difference in means without row resampling."""
    x = pd.to_numeric(treatment, errors="coerce").dropna().to_numpy(dtype=float)
    y = pd.to_numeric(reference, errors="coerce").dropna().to_numpy(dtype=float)
    rng = np.random.default_rng(seed)
    draws: list[np.ndarray] = []
    remaining = reps
    while remaining:
        size = min(chunk_size, remaining)
        wx = rng.exponential(size=(size, len(x)))
        wy = rng.exponential(size=(size, len(y)))
        mx = (wx @ x) / wx.sum(axis=1)
        my = (wy @ y) / wy.sum(axis=1)
        draws.append(mx - my)
        remaining -= size
    values = np.concatenate(draws)
    return float(np.mean(x) - np.mean(y)), float(np.quantile(values, 0.025)), float(np.quantile(values, 0.975))


def campaign_roi(incremental_net_profit: float, campaign_cost: float) -> float:
    """Return incremental net profit divided by cashback plus contact cost."""
    return float(incremental_net_profit / campaign_cost) if campaign_cost else np.nan

