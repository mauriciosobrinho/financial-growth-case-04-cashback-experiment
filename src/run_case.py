"""End-to-end causal analysis for the cashback randomized experiment."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

from src.experiment_utils import (
    approximate_binary_mde,
    approximate_continuous_mde,
    approximate_observed_power,
    bayesian_bootstrap_difference,
    binary_contrast,
    campaign_roi,
    continuous_contrast,
    cuped_adjust,
    holm_adjust,
    standardized_mean_difference,
)


ROOT = Path(__file__).resolve().parents[1]
RAW_PATH = ROOT / "data" / "raw" / "case_04_cashback_experiment_raw.csv"
FIGURES = ROOT / "outputs" / "figures"
TABLES = ROOT / "outputs" / "tables"
METRICS = ROOT / "outputs" / "metrics"
SEED = 20260927
ARM_ORDER = ["control", "cashback_5", "cashback_10"]
ARM_LABELS = {"control": "Control", "cashback_5": "Cashback 5%", "cashback_10": "Cashback 10%"}
COLORS = {"control": "#64748B", "cashback_5": "#0F766E", "cashback_10": "#1D4ED8"}

PRE_NUMERIC = [
    "customer_tenure_months",
    "days_since_last_transaction",
    "txn_count_30d_pre",
    "txn_count_90d_pre",
    "spend_30d_pre",
    "spend_90d_pre",
    "avg_ticket_30d_pre",
    "avg_ticket_90d_pre",
    "pix_count_30d_pre",
    "pix_value_30d_pre",
    "avg_balance_30d_pre",
    "min_balance_30d_pre",
    "max_balance_30d_pre",
    "card_spend_30d_pre",
    "card_utilization_pre",
    "credit_limit",
    "num_products",
    "app_sessions_30d_pre",
    "app_sessions_90d_pre",
    "days_since_last_login_pre",
    "push_open_rate_90d",
    "email_open_rate_90d",
    "campaigns_received_90d",
    "campaign_clicks_90d",
    "previous_offer_acceptance_rate",
    "support_contacts_90d",
    "complaints_90d_pre",
    "refunds_90d_pre",
    "chargebacks_90d_pre",
    "gross_margin_30d_pre",
]

PRE_CATEGORICAL = [
    "customer_segment",
    "region",
    "merchant_flag",
    "merchant_segment",
    "income_band",
    "relationship_tier",
    "has_credit_card",
    "has_loan",
    "has_investment",
    "has_insurance",
    "has_pos",
]

BINARY_OUTCOMES = [
    "purchased_30d",
    "complaint_30d",
    "refund_flag_30d",
    "chargeback_flag_30d",
    "churn_60d",
]

CONTINUOUS_OUTCOMES = [
    "txn_count_30d_post",
    "spend_30d_post",
    "gross_margin_30d",
    "cashback_cost",
    "campaign_contact_cost",
    "net_margin_30d",
    "refund_value_30d",
    "chargeback_value_30d",
]

PRIMARY_PAIRS = [
    ("cashback_5", "control"),
    ("cashback_10", "control"),
    ("cashback_10", "cashback_5"),
]

# These are explicit case assumptions for a broad rollout. Product and Risk must
# approve them before a real experiment starts.
GUARDRAIL_THRESHOLDS_PP = {
    "complaint_30d": 0.015,
    "refund_flag_30d": 0.010,
    "chargeback_flag_30d": 0.005,
    "churn_60d": 0.005,
}


def ensure_directories() -> None:
    for path in [FIGURES, TABLES, METRICS]:
        path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def read_data() -> pd.DataFrame:
    df = pd.read_csv(RAW_PATH)
    df["reference_date"] = pd.to_datetime(df["reference_date"])
    df["campaign_wave"] = df["campaign_wave"].astype(str)
    df["treatment_arm"] = pd.Categorical(df["treatment_arm"], categories=ARM_ORDER, ordered=True)
    return df


def data_quality(df: pd.DataFrame, development: pd.DataFrame) -> dict:
    """Audit the full assignment/pre-treatment data and only development outcomes."""
    expected_net = (
        development["gross_margin_30d"]
        - development["cashback_cost"]
        - development["campaign_contact_cost"]
    )
    profile = {
        "rows": int(len(df)),
        "columns": int(df.shape[1]),
        "unique_customers": int(df["customer_id"].nunique()),
        "exact_duplicates": int(df.duplicated().sum()),
        "duplicate_customers": int(df["customer_id"].duplicated().sum()),
        "campaign_waves": int(df["campaign_wave"].nunique()),
        "sentinel_9999_days_since_last_login": int((df["days_since_last_login_pre"] == 9999).sum()),
        "outcome_integrity_scope": "development_waves_1_5_before_policy_freeze",
        "max_net_margin_reconciliation_error": float(
            (development["net_margin_30d"] - expected_net).abs().max()
        ),
    }
    missing = (
        df.isna()
        .mean()
        .rename("missing_rate")
        .reset_index(name="missing_rate")
        .rename(columns={"index": "feature"})
        .sort_values("missing_rate", ascending=False)
    )
    missing.to_csv(TABLES / "data_quality_missing_overall.csv", index=False)
    missing_arm = (
        df.groupby("treatment_arm", observed=True)[df.columns[df.isna().any()].tolist()]
        .apply(lambda x: x.isna().mean())
        .reset_index()
    )
    missing_arm.to_csv(TABLES / "data_quality_missing_by_arm.csv", index=False)
    quantile_cols = ["spend_30d_pre", "spend_30d_post", "gross_margin_30d", "net_margin_30d"]
    quantiles = development[quantile_cols].quantile([0, 0.01, 0.5, 0.95, 0.99, 0.999, 1]).T
    quantiles.columns = [f"q_{str(q).replace('.', '_')}" for q in [0, 0.01, 0.5, 0.95, 0.99, 0.999, 1]]
    quantiles.reset_index().rename(columns={"index": "feature"}).to_csv(
        TABLES / "financial_outlier_quantiles.csv", index=False
    )
    write_json(METRICS / "data_quality_summary.json", profile)
    return profile


def randomization_checks(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    counts = pd.crosstab(df["campaign_wave"], df["treatment_arm"]).reindex(columns=ARM_ORDER)
    counts.to_csv(TABLES / "assignment_by_wave.csv")
    global_counts = df["treatment_arm"].value_counts().reindex(ARM_ORDER)
    chi_global = stats.chisquare(global_counts.to_numpy(), f_exp=np.repeat(len(df) / 3, 3))
    chi_wave = stats.chi2_contingency(counts.to_numpy())

    smd_rows: list[dict] = []
    for feature in PRE_NUMERIC:
        clean = df[feature].replace(9999, np.nan) if feature == "days_since_last_login_pre" else df[feature]
        for arm, reference in PRIMARY_PAIRS:
            smd_rows.append(
                {
                    "feature": feature,
                    "contrast": f"{arm}_vs_{reference}",
                    "smd": standardized_mean_difference(
                        clean[df["treatment_arm"] == arm], clean[df["treatment_arm"] == reference]
                    ),
                }
            )
    smd = pd.DataFrame(smd_rows)
    smd.to_csv(TABLES / "pre_treatment_numeric_balance_smd.csv", index=False)

    cat_rows: list[dict] = []
    for feature in PRE_CATEGORICAL:
        shares = pd.crosstab(df[feature].fillna("Missing"), df["treatment_arm"], normalize="columns")
        for arm, reference in PRIMARY_PAIRS:
            cat_rows.append(
                {
                    "feature": feature,
                    "contrast": f"{arm}_vs_{reference}",
                    "max_absolute_share_difference": float((shares[arm] - shares[reference]).abs().max()),
                }
            )
    cat_balance = pd.DataFrame(cat_rows)
    cat_balance.to_csv(TABLES / "pre_treatment_categorical_balance.csv", index=False)

    summary = {
        "global_sample_ratio_chi_square": float(chi_global.statistic),
        "global_sample_ratio_p_value": float(chi_global.pvalue),
        "assignment_by_wave_chi_square": float(chi_wave.statistic),
        "assignment_by_wave_p_value": float(chi_wave.pvalue),
        "max_absolute_numeric_smd": float(smd["smd"].abs().max()),
        "numeric_features_above_0_10_smd": int((smd["smd"].abs() > 0.10).sum()),
        "max_categorical_share_difference": float(cat_balance["max_absolute_share_difference"].max()),
    }
    write_json(METRICS / "randomization_checks.json", summary)
    return smd, cat_balance, summary


def compliance_table(df: pd.DataFrame) -> pd.DataFrame:
    result = (
        df.groupby("treatment_arm", observed=True)
        .agg(
            assigned=("customer_id", "size"),
            delivery_rate=("message_delivered", "mean"),
            activation_rate=("offer_activated", "mean"),
            conversion_rate=("purchased_30d", "mean"),
        )
        .reset_index()
    )
    result.to_csv(TABLES / "assignment_delivery_activation.csv", index=False)
    return result


def temporal_roles(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    waves = sorted(df["campaign_wave"].unique())
    development = df[df["campaign_wave"].isin(waves[:5])].copy()
    validation = df[df["campaign_wave"] == waves[5]].copy()
    holdout = df[df["campaign_wave"] == waves[6]].copy()
    split = pd.DataFrame(
        [
            {"role": "Development", "waves": ", ".join(waves[:5]), "rows": len(development)},
            {"role": "Temporal validation", "waves": waves[5], "rows": len(validation)},
            {"role": "Final holdout", "waves": waves[6], "rows": len(holdout)},
        ]
    )
    split.to_csv(TABLES / "temporal_protocol.csv", index=False)
    return development, validation, holdout, split


def arm_summary(frame: pd.DataFrame, cohort: str) -> pd.DataFrame:
    metrics = [
        "purchased_30d",
        "txn_count_30d_post",
        "spend_30d_post",
        "gross_margin_30d",
        "cashback_cost",
        "campaign_contact_cost",
        "net_margin_30d",
        "complaint_30d",
        "refund_flag_30d",
        "refund_value_30d",
        "chargeback_flag_30d",
        "chargeback_value_30d",
        "churn_60d",
    ]
    result = frame.groupby("treatment_arm", observed=True)[metrics].mean().reset_index()
    result.insert(1, "assigned_customers", frame.groupby("treatment_arm", observed=True).size().to_numpy())
    result.insert(0, "cohort", cohort)
    return result


def contrast_table(frame: pd.DataFrame, cohort: str, metrics: list[str]) -> pd.DataFrame:
    rows: list[dict] = []
    for metric in metrics:
        for arm, reference in PRIMARY_PAIRS:
            x = frame.loc[frame["treatment_arm"] == arm, metric]
            y = frame.loc[frame["treatment_arm"] == reference, metric]
            result = binary_contrast(x, y) if metric in BINARY_OUTCOMES else continuous_contrast(x, y)
            rows.append(
                {
                    "cohort": cohort,
                    "metric": metric,
                    "treatment": arm,
                    "reference": reference,
                    "estimate": result.estimate,
                    "standard_error": result.standard_error,
                    "ci_low": result.ci_low,
                    "ci_high": result.ci_high,
                    "p_value": result.p_value,
                    "relative_effect": result.relative_effect,
                    "effect_size": result.effect_size,
                    "observed_power_diagnostic": approximate_observed_power(result.estimate, result.standard_error),
                }
            )
    table = pd.DataFrame(rows)
    table["p_value_holm"] = table.groupby("metric")["p_value"].transform(lambda values: holm_adjust(values.to_numpy()))
    return table


def power_and_mde(development: pd.DataFrame) -> pd.DataFrame:
    control = development[development["treatment_arm"] == "control"]
    rows: list[dict] = []
    for arm in ["cashback_5", "cashback_10"]:
        treated = development[development["treatment_arm"] == arm]
        baseline = float(control["purchased_30d"].mean())
        conversion_result = binary_contrast(treated["purchased_30d"], control["purchased_30d"])
        pooled_sd = np.sqrt(
            (treated["net_margin_30d"].var(ddof=1) + control["net_margin_30d"].var(ddof=1)) / 2
        )
        net_result = continuous_contrast(treated["net_margin_30d"], control["net_margin_30d"])
        rows.extend(
            [
                {
                    "treatment": arm,
                    "metric": "purchased_30d",
                    "n_treatment": len(treated),
                    "n_control": len(control),
                    "baseline": baseline,
                    "mde_80pct_power": approximate_binary_mde(baseline, len(treated), len(control)),
                    "observed_effect": conversion_result.estimate,
                    "observed_power_diagnostic": approximate_observed_power(
                        conversion_result.estimate, conversion_result.standard_error
                    ),
                },
                {
                    "treatment": arm,
                    "metric": "net_margin_30d",
                    "n_treatment": len(treated),
                    "n_control": len(control),
                    "baseline": float(control["net_margin_30d"].mean()),
                    "mde_80pct_power": approximate_continuous_mde(
                        pooled_sd, len(treated), len(control)
                    ),
                    "observed_effect": net_result.estimate,
                    "observed_power_diagnostic": approximate_observed_power(net_result.estimate, net_result.standard_error),
                },
            ]
        )
    result = pd.DataFrame(rows)
    result.to_csv(METRICS / "power_and_mde_diagnostics.csv", index=False)
    return result


def cuped_analysis(development: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    mappings = {
        "spend_30d_post": "spend_30d_pre",
        "txn_count_30d_post": "txn_count_30d_pre",
        "gross_margin_30d": "gross_margin_30d_pre",
        "net_margin_30d": "gross_margin_30d_pre",
    }
    result_rows: list[dict] = []
    contrast_rows: list[dict] = []
    control_mask = development["treatment_arm"] == "control"
    for outcome, covariate in mappings.items():
        adjusted, theta, reduction = cuped_adjust(
            development[outcome],
            development[covariate],
            theta_sample=development.loc[control_mask, outcome].to_numpy(),
            theta_covariate=development.loc[control_mask, covariate].to_numpy(),
        )
        adjusted_name = f"{outcome}_cuped"
        development[adjusted_name] = adjusted
        correlation = development[[outcome, covariate]].corr().iloc[0, 1]
        result_rows.append(
            {
                "outcome": outcome,
                "covariate": covariate,
                "theta_control_development": theta,
                "correlation": correlation,
                "variance_reduction": reduction,
            }
        )
        for arm, reference in PRIMARY_PAIRS:
            contrast = continuous_contrast(
                development.loc[development["treatment_arm"] == arm, adjusted_name],
                development.loc[development["treatment_arm"] == reference, adjusted_name],
            )
            contrast_rows.append(
                {
                    "outcome": outcome,
                    "covariate": covariate,
                    "treatment": arm,
                    "reference": reference,
                    "estimate_cuped": contrast.estimate,
                    "standard_error_cuped": contrast.standard_error,
                    "ci_low_cuped": contrast.ci_low,
                    "ci_high_cuped": contrast.ci_high,
                    "p_value_cuped": contrast.p_value,
                }
            )
    diagnostics = pd.DataFrame(result_rows)
    contrasts = pd.DataFrame(contrast_rows)
    contrasts["p_value_holm_cuped"] = contrasts.groupby("outcome")["p_value_cuped"].transform(
        lambda values: holm_adjust(values.to_numpy())
    )
    diagnostics.to_csv(METRICS / "cuped_variance_reduction.csv", index=False)
    contrasts.to_csv(METRICS / "cuped_contrasts.csv", index=False)
    return diagnostics, contrasts


def bootstrap_primary_kpi(development: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for i, (arm, reference) in enumerate(PRIMARY_PAIRS):
        estimate, ci_low, ci_high = bayesian_bootstrap_difference(
            development.loc[development["treatment_arm"] == arm, "net_margin_30d"],
            development.loc[development["treatment_arm"] == reference, "net_margin_30d"],
            reps=300,
            seed=SEED + i,
            chunk_size=10,
        )
        rows.append(
            {
                "metric": "net_margin_30d",
                "treatment": arm,
                "reference": reference,
                "estimate": estimate,
                "bootstrap_ci_low": ci_low,
                "bootstrap_ci_high": ci_high,
                "method": "Bayesian bootstrap, 300 draws",
            }
        )
    result = pd.DataFrame(rows)
    result.to_csv(METRICS / "net_margin_bootstrap_intervals.csv", index=False)
    return result


def economics(frame: pd.DataFrame, cohort: str) -> pd.DataFrame:
    grouped = (
        frame.groupby("treatment_arm", observed=True)
        .agg(
            assigned_customers=("customer_id", "size"),
            purchases=("purchased_30d", "sum"),
            conversion_rate=("purchased_30d", "mean"),
            total_transactions=("txn_count_30d_post", "sum"),
            total_spend=("spend_30d_post", "sum"),
            total_gross_margin=("gross_margin_30d", "sum"),
            total_cashback_cost=("cashback_cost", "sum"),
            total_contact_cost=("campaign_contact_cost", "sum"),
            total_net_margin=("net_margin_30d", "sum"),
            mean_net_margin=("net_margin_30d", "mean"),
        )
        .reset_index()
    )
    control = grouped[grouped["treatment_arm"] == "control"].iloc[0]
    grouped["incremental_conversion_rate_vs_control"] = grouped["conversion_rate"] - control["conversion_rate"]
    grouped["incremental_net_margin_per_customer_vs_control"] = grouped["mean_net_margin"] - control["mean_net_margin"]
    grouped["incremental_net_profit_total_vs_control"] = (
        grouped["incremental_net_margin_per_customer_vs_control"] * grouped["assigned_customers"]
    )
    grouped["campaign_cost_total"] = grouped["total_cashback_cost"] + grouped["total_contact_cost"]
    grouped["roi_incremental_net_profit_over_campaign_cost"] = grouped.apply(
        lambda row: campaign_roi(row["incremental_net_profit_total_vs_control"], row["campaign_cost_total"]), axis=1
    )
    grouped.insert(0, "cohort", cohort)
    return grouped


def guardrail_decision(development: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    contrasts = contrast_table(development, "development_waves_1_5", list(GUARDRAIL_THRESHOLDS_PP))
    rows: list[dict] = []
    for arm in ["cashback_5", "cashback_10"]:
        for metric, threshold in GUARDRAIL_THRESHOLDS_PP.items():
            record = contrasts[
                (contrasts["metric"] == metric)
                & (contrasts["treatment"] == arm)
                & (contrasts["reference"] == "control")
            ].iloc[0]
            rows.append(
                {
                    "treatment": arm,
                    "guardrail": metric,
                    "absolute_change": record["estimate"],
                    "ci_low": record["ci_low"],
                    "ci_high": record["ci_high"],
                    "p_value_holm": record["p_value_holm"],
                    "illustrative_max_deterioration": threshold,
                    "passes_threshold": bool(record["estimate"] <= threshold),
                }
            )
    table = pd.DataFrame(rows)
    table.to_csv(TABLES / "development_guardrail_decision.csv", index=False)
    pass_by_arm = table.groupby("treatment")["passes_threshold"].all().to_dict()
    economics_table = economics(development, "development_waves_1_5")
    eligible = [arm for arm in ["cashback_5", "cashback_10"] if pass_by_arm.get(arm, False)]
    if not eligible:
        chosen = "control"
        rationale = "Neither treatment met the illustrative guardrail thresholds."
    else:
        eligible_rows = economics_table[economics_table["treatment_arm"].isin(eligible)]
        chosen = str(eligible_rows.sort_values("incremental_net_profit_total_vs_control", ascending=False).iloc[0]["treatment_arm"])
        rationale = (
            "Choose the guardrail-eligible treatment with the highest incremental net profit in waves 1-5. "
            "The thresholds are explicit case assumptions and require Product and Risk approval before rollout."
        )
    policy = {
        "decision_stage": "frozen_before_wave_7_holdout",
        "development_waves": ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05"],
        "temporal_validation_wave": "2026-06",
        "final_holdout_wave": "2026-07",
        "primary_estimand": "Intention-to-Treat",
        "primary_kpi": "net_margin_30d",
        "chosen_policy": chosen,
        "guardrail_thresholds_absolute": GUARDRAIL_THRESHOLDS_PP,
        "guardrail_pass_by_arm": {str(k): bool(v) for k, v in pass_by_arm.items()},
        "rationale": rationale,
    }
    policy["configuration_sha256"] = hashlib.sha256(
        json.dumps(policy, sort_keys=True, ensure_ascii=True).encode("utf-8")
    ).hexdigest()
    write_json(METRICS / "policy_freeze_record.json", policy)
    return table, policy


def wave_effects(df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for wave, frame in df.groupby("campaign_wave"):
        for arm in ["cashback_5", "cashback_10"]:
            for metric in ["purchased_30d", "net_margin_30d"]:
                result = (
                    binary_contrast(
                        frame.loc[frame["treatment_arm"] == arm, metric],
                        frame.loc[frame["treatment_arm"] == "control", metric],
                    )
                    if metric == "purchased_30d"
                    else continuous_contrast(
                        frame.loc[frame["treatment_arm"] == arm, metric],
                        frame.loc[frame["treatment_arm"] == "control", metric],
                    )
                )
                rows.append(
                    {
                        "campaign_wave": wave,
                        "treatment": arm,
                        "metric": metric,
                        "estimate": result.estimate,
                        "ci_low": result.ci_low,
                        "ci_high": result.ci_high,
                        "p_value": result.p_value,
                    }
                )
    result = pd.DataFrame(rows)
    result.to_csv(METRICS / "effects_by_campaign_wave.csv", index=False)
    return result


def heterogeneity(development: pd.DataFrame, chosen_arm: str) -> pd.DataFrame:
    frame = development.copy()
    frame["baseline_spend_group"] = pd.qcut(
        frame["spend_30d_pre"], q=4, labels=["Q1", "Q2", "Q3", "Q4"], duplicates="drop"
    )
    dimensions = ["customer_segment", "merchant_flag", "relationship_tier", "baseline_spend_group"]
    rows: list[dict] = []
    for dimension in dimensions:
        for level, segment in frame.groupby(dimension, observed=True):
            treated = segment[segment["treatment_arm"] == chosen_arm]
            control = segment[segment["treatment_arm"] == "control"]
            if len(treated) < 300 or len(control) < 300:
                continue
            net = continuous_contrast(treated["net_margin_30d"], control["net_margin_30d"])
            conv = binary_contrast(treated["purchased_30d"], control["purchased_30d"])
            rows.append(
                {
                    "dimension": dimension,
                    "level": str(level),
                    "n_treatment": len(treated),
                    "n_control": len(control),
                    "net_margin_effect": net.estimate,
                    "net_margin_ci_low": net.ci_low,
                    "net_margin_ci_high": net.ci_high,
                    "conversion_effect": conv.estimate,
                    "conversion_ci_low": conv.ci_low,
                    "conversion_ci_high": conv.ci_high,
                    "status": "exploratory_hypothesis_generation",
                }
            )
    result = pd.DataFrame(rows)
    result.to_csv(TABLES / "development_heterogeneous_effects.csv", index=False)
    return result


def save_figures(
    df: pd.DataFrame,
    smd: pd.DataFrame,
    development_contrasts: pd.DataFrame,
    cuped_diagnostics: pd.DataFrame,
    economics_all: pd.DataFrame,
    guardrails: pd.DataFrame,
    wave_table: pd.DataFrame,
    heterogeneity_table: pd.DataFrame,
    compliance: pd.DataFrame,
    chosen_arm: str,
) -> None:
    plt.style.use("seaborn-v0_8-whitegrid")

    counts = pd.crosstab(df["campaign_wave"], df["treatment_arm"]).reindex(columns=ARM_ORDER)
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    counts.plot(kind="bar", ax=axes[0], color=[COLORS[a] for a in ARM_ORDER])
    axes[0].set_title("Clientes por braço e onda")
    axes[0].set_xlabel("Onda")
    axes[0].set_ylabel("Clientes")
    axes[0].legend([ARM_LABELS[a] for a in ARM_ORDER], frameon=False)
    axes[1].hist(smd["smd"].dropna(), bins=30, color="#0F766E", alpha=0.85)
    axes[1].axvline(-0.1, color="#DC2626", linestyle="--")
    axes[1].axvline(0.1, color="#DC2626", linestyle="--", label="|SMD| = 0,10")
    axes[1].set_title("Balanceamento das covariáveis pré-tratamento")
    axes[1].set_xlabel("Standardized Mean Difference")
    axes[1].set_ylabel("Quantidade de comparações")
    axes[1].legend(frameon=False)
    fig.tight_layout()
    fig.savefig(FIGURES / "01_randomization_and_balance.png", dpi=170, bbox_inches="tight")
    plt.close(fig)

    missing_by_wave = df.groupby("campaign_wave")[["push_open_rate_90d", "email_open_rate_90d", "support_contacts_90d"]].apply(
        lambda x: x.isna().mean()
    )
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    missing_by_wave.plot(ax=axes[0], marker="o")
    axes[0].set_title("Missing por onda")
    axes[0].set_xlabel("Onda")
    axes[0].set_ylabel("Proporção missing")
    axes[0].tick_params(axis="x", rotation=45)
    axes[0].legend(frameon=False)
    axes[1].boxplot(
        [np.log1p(df.loc[df["treatment_arm"] == arm, "spend_30d_post"]) for arm in ARM_ORDER],
        tick_labels=[ARM_LABELS[a] for a in ARM_ORDER],
        showfliers=False,
    )
    axes[1].set_title("Spend pós-tratamento em escala log")
    axes[1].set_ylabel("log(1 + spend)")
    fig.tight_layout()
    fig.savefig(FIGURES / "02_data_quality_and_long_tails.png", dpi=170, bbox_inches="tight")
    plt.close(fig)

    conversion = development_contrasts[
        (development_contrasts["metric"] == "purchased_30d")
        & (development_contrasts["reference"] == "control")
    ].copy()
    net = development_contrasts[
        (development_contrasts["metric"] == "net_margin_30d")
        & (development_contrasts["reference"] == "control")
    ].copy()
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    for ax, table, title, scale, xlabel in [
        (axes[0], conversion, "Efeito ITT em conversão, ondas 1–5", 100, "Diferença absoluta (p.p.)"),
        (axes[1], net, "Efeito ITT em margem líquida, ondas 1–5", 1, "Diferença média por cliente (R$)"),
    ]:
        y = np.arange(len(table))
        ax.errorbar(
            table["estimate"] * scale,
            y,
            xerr=[(table["estimate"] - table["ci_low"]) * scale, (table["ci_high"] - table["estimate"]) * scale],
            fmt="o",
            color="#0F766E",
            capsize=4,
        )
        ax.axvline(0, color="#475569", linewidth=1)
        ax.set_yticks(y, [ARM_LABELS[a] for a in table["treatment"]])
        ax.set_title(title)
        ax.set_xlabel(xlabel)
    fig.tight_layout()
    fig.savefig(FIGURES / "03_primary_causal_effects.png", dpi=170, bbox_inches="tight")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 5))
    values = cuped_diagnostics.set_index("outcome")["variance_reduction"].sort_values()
    ax.barh(values.index, values.values * 100, color="#1D4ED8")
    ax.set_title("Redução de variância com CUPED")
    ax.set_xlabel("Redução de variância (%)")
    ax.set_ylabel("Outcome")
    for i, value in enumerate(values.values * 100):
        ax.text(value + 0.3, i, f"{value:.1f}%", va="center")
    fig.tight_layout()
    fig.savefig(FIGURES / "04_cuped_variance_reduction.png", dpi=170, bbox_inches="tight")
    plt.close(fig)

    wave_net = wave_table[wave_table["metric"] == "net_margin_30d"]
    fig, ax = plt.subplots(figsize=(11, 5))
    for arm in ["cashback_5", "cashback_10"]:
        part = wave_net[wave_net["treatment"] == arm]
        ax.errorbar(
            part["campaign_wave"],
            part["estimate"],
            yerr=[part["estimate"] - part["ci_low"], part["ci_high"] - part["estimate"]],
            marker="o",
            capsize=3,
            label=ARM_LABELS[arm],
            color=COLORS[arm],
        )
    ax.axhline(0, color="#475569", linewidth=1)
    ax.axvline("2026-06", color="#F59E0B", linestyle="--", label="Validação temporal")
    ax.axvline("2026-07", color="#DC2626", linestyle=":", label="Holdout final")
    ax.set_title("Estabilidade temporal do efeito em margem líquida")
    ax.set_xlabel("Onda")
    ax.set_ylabel("Efeito médio versus controle (R$ por cliente)")
    ax.legend(frameon=False, ncol=2)
    fig.tight_layout()
    fig.savefig(FIGURES / "05_temporal_stability.png", dpi=170, bbox_inches="tight")
    plt.close(fig)

    full_economics = economics_all[economics_all["cohort"] == "all_waves"].copy()
    treated = full_economics[full_economics["treatment_arm"] != "control"]
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    axes[0].bar(
        [ARM_LABELS[a] for a in treated["treatment_arm"]],
        treated["incremental_net_profit_total_vs_control"] / 1_000_000,
        color=[COLORS[a] for a in treated["treatment_arm"]],
    )
    axes[0].set_title("Lucro incremental líquido")
    axes[0].set_ylabel("R$ milhões")
    axes[1].bar(
        [ARM_LABELS[a] for a in treated["treatment_arm"]],
        treated["roi_incremental_net_profit_over_campaign_cost"],
        color=[COLORS[a] for a in treated["treatment_arm"]],
    )
    axes[1].set_title("ROI sobre cashback e contato")
    axes[1].set_ylabel("Incremental net profit / campaign cost")
    fig.tight_layout()
    fig.savefig(FIGURES / "06_incremental_profit_and_roi.png", dpi=170, bbox_inches="tight")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(11, 5))
    plot_guard = guardrails.copy()
    plot_guard["change_pp"] = plot_guard["absolute_change"] * 100
    pivot = plot_guard.pivot(index="guardrail", columns="treatment", values="change_pp")
    pivot[["cashback_5", "cashback_10"]].plot(
        kind="bar", ax=ax, color=[COLORS["cashback_5"], COLORS["cashback_10"]]
    )
    ax.axhline(0, color="#475569", linewidth=1)
    ax.set_title("Mudança dos guardrails versus controle, ondas 1–5")
    ax.set_xlabel("Guardrail")
    ax.set_ylabel("Diferença absoluta (p.p.)")
    ax.legend(["Cashback 5%", "Cashback 10%"], frameon=False)
    ax.tick_params(axis="x", rotation=20)
    fig.tight_layout()
    fig.savefig(FIGURES / "07_guardrails.png", dpi=170, bbox_inches="tight")
    plt.close(fig)

    if not heterogeneity_table.empty:
        top = heterogeneity_table.reindex(
            heterogeneity_table["net_margin_effect"].abs().sort_values(ascending=False).index
        ).head(12)
        labels = top["dimension"] + ": " + top["level"]
        fig, ax = plt.subplots(figsize=(10, 6))
        y = np.arange(len(top))
        ax.errorbar(
            top["net_margin_effect"],
            y,
            xerr=[top["net_margin_effect"] - top["net_margin_ci_low"], top["net_margin_ci_high"] - top["net_margin_effect"]],
            fmt="o",
            color=COLORS.get(chosen_arm, "#0F766E"),
            capsize=3,
        )
        ax.axvline(0, color="#475569", linewidth=1)
        ax.set_yticks(y, labels)
        ax.set_title(f"Heterogeneidade exploratória: {ARM_LABELS.get(chosen_arm, chosen_arm)}")
        ax.set_xlabel("Efeito em margem líquida versus controle (R$)")
        fig.tight_layout()
        fig.savefig(FIGURES / "08_exploratory_heterogeneity.png", dpi=170, bbox_inches="tight")
        plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 5))
    x = np.arange(len(compliance))
    width = 0.25
    ax.bar(x - width, compliance["delivery_rate"] * 100, width, label="Delivery", color="#94A3B8")
    ax.bar(x, compliance["activation_rate"] * 100, width, label="Activation", color="#0F766E")
    ax.bar(x + width, compliance["conversion_rate"] * 100, width, label="Conversion", color="#1D4ED8")
    ax.set_xticks(x, [ARM_LABELS[str(a)] for a in compliance["treatment_arm"]])
    ax.set_ylabel("Taxa (%)")
    ax.set_title("Assignment, delivery, activation e outcome")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(FIGURES / "09_compliance_and_conversion.png", dpi=170, bbox_inches="tight")
    plt.close(fig)


def main() -> dict:
    ensure_directories()
    print("Comentário Técnico: carregando somente a base pública do experimento.")
    df = read_data()
    development, validation, holdout, split = temporal_roles(df)
    profile = data_quality(df, development)
    smd, _, randomization = randomization_checks(df)

    print("Comentário Técnico: estimando ITT nas ondas 1–5 e preservando a onda 7.")
    development_summary = arm_summary(development, "development_waves_1_5")
    development_contrasts = contrast_table(
        development, "development_waves_1_5", BINARY_OUTCOMES + CONTINUOUS_OUTCOMES
    )
    development_contrasts.to_csv(METRICS / "development_itt_contrasts.csv", index=False)
    development_summary.to_csv(TABLES / "development_arm_summary.csv", index=False)
    power = power_and_mde(development)
    cuped_diagnostics, cuped_contrasts = cuped_analysis(development)
    bootstrap = bootstrap_primary_kpi(development)
    guardrails, policy = guardrail_decision(development)

    print("Comentário Técnico: política congelada antes da avaliação do holdout final.")
    chosen = policy["chosen_policy"]
    validation_summary = arm_summary(validation, "temporal_validation_wave_6")
    validation_contrasts = contrast_table(
        validation, "temporal_validation_wave_6", ["purchased_30d", "net_margin_30d"] + list(GUARDRAIL_THRESHOLDS_PP)
    )
    validation_summary.to_csv(TABLES / "validation_arm_summary.csv", index=False)
    validation_contrasts.to_csv(METRICS / "validation_itt_contrasts.csv", index=False)

    print("Comentário Técnico: abrindo a onda 7 uma única vez para o teste final.")
    holdout_summary = arm_summary(holdout, "final_holdout_wave_7")
    holdout_contrasts = contrast_table(
        holdout, "final_holdout_wave_7", ["purchased_30d", "net_margin_30d"] + list(GUARDRAIL_THRESHOLDS_PP)
    )
    holdout_summary.to_csv(TABLES / "holdout_arm_summary.csv", index=False)
    holdout_contrasts.to_csv(METRICS / "holdout_itt_contrasts.csv", index=False)

    # Full-period compliance and outcome summaries are allowed only after the
    # policy record exists and the final holdout has been opened.
    compliance = compliance_table(df)

    economics_all = pd.concat(
        [
            economics(development, "development_waves_1_5"),
            economics(validation, "temporal_validation_wave_6"),
            economics(holdout, "final_holdout_wave_7"),
            economics(df, "all_waves"),
        ],
        ignore_index=True,
    )
    economics_all.to_csv(TABLES / "business_economics_by_cohort.csv", index=False)
    wave_table = wave_effects(df)
    heterogeneity_table = heterogeneity(development, chosen)

    save_figures(
        df,
        smd,
        development_contrasts,
        cuped_diagnostics,
        economics_all,
        guardrails,
        wave_table,
        heterogeneity_table,
        compliance,
        chosen,
    )

    all_waves_econ = economics_all[economics_all["cohort"] == "all_waves"].set_index("treatment_arm")
    chosen_holdout = holdout_contrasts[
        (holdout_contrasts["treatment"] == chosen)
        & (holdout_contrasts["reference"] == "control")
    ].set_index("metric")
    summary = {
        "data": profile,
        "randomization": randomization,
        "temporal_protocol": split.to_dict(orient="records"),
        "primary_estimand": "Intention-to-Treat",
        "chosen_policy": chosen,
        "chosen_policy_label": ARM_LABELS.get(chosen, chosen),
        "development_policy_rationale": policy["rationale"],
        "holdout_chosen_policy": {
            "conversion_effect_absolute": float(chosen_holdout.loc["purchased_30d", "estimate"]),
            "conversion_ci": [
                float(chosen_holdout.loc["purchased_30d", "ci_low"]),
                float(chosen_holdout.loc["purchased_30d", "ci_high"]),
            ],
            "net_margin_effect_per_customer": float(chosen_holdout.loc["net_margin_30d", "estimate"]),
            "net_margin_ci": [
                float(chosen_holdout.loc["net_margin_30d", "ci_low"]),
                float(chosen_holdout.loc["net_margin_30d", "ci_high"]),
            ],
        },
        "all_waves_economics": {
            arm: {
                "conversion_rate": float(all_waves_econ.loc[arm, "conversion_rate"]),
                "mean_net_margin": float(all_waves_econ.loc[arm, "mean_net_margin"]),
                "incremental_net_profit_total_vs_control": float(
                    all_waves_econ.loc[arm, "incremental_net_profit_total_vs_control"]
                ),
                "roi_incremental_net_profit_over_campaign_cost": float(
                    all_waves_econ.loc[arm, "roi_incremental_net_profit_over_campaign_cost"]
                )
                if arm != "control"
                else None,
            }
            for arm in ARM_ORDER
        },
        "cuped_variance_reduction": {
            row["outcome"]: float(row["variance_reduction"]) for _, row in cuped_diagnostics.iterrows()
        },
        "bootstrap_primary_kpi": bootstrap.to_dict(orient="records"),
        "power_and_mde": power.to_dict(orient="records"),
        "mandatory_conclusion": (
            "Maior conversão não implica maior valor econômico. A decisão deve ser baseada em lucro incremental "
            "líquido, incerteza estatística, guardrails e estabilidade do efeito."
        ),
    }
    write_json(METRICS / "executive_summary.json", summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary


if __name__ == "__main__":
    main()
