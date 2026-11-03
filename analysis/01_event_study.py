"""
Step 3a: event study and difference-in-differences for the June 2024 diesel change.

Question: after diesel rose in Peninsular Malaysia on 10 June 2024 (but not in
Sabah, Sarawak or Labuan), did grocery prices in the Peninsula rise MORE than the
same items in East Malaysia?

Input : warehouse table mart_diesel__item_region_week (built by dbt)
Output: outputs/raw_trends.png         average price change by region, week by week
        outputs/event_study.png        the event study chart
        outputs/event_study_coefs.csv  the numbers behind the chart
        printed DiD estimates

Run from the project root:  python analysis/01_event_study.py
"""

import re
from pathlib import Path

import duckdb
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyfixest as pf

DB = Path("warehouse/pump_to_pasar.duckdb")
OUT = Path("outputs")
BIN_LIMIT = 52  # weeks; event weeks beyond +/-52 are grouped into the end bins


def week_of(term: str) -> int:
    """'event_bin::-12:peninsular' -> -12"""
    return int(re.search(r"::(-?\d+):", term).group(1))


# Standard errors are clustered by item: the same item's prices are correlated
# over time, so its weeks are not independent observations. (Clustering by region
# is impossible with only two regions; step 3b tests region-wide shocks with
# placebo dates instead.)
VCOV = {"CRV1": "item_id"}


def load_panel() -> pd.DataFrame:
    con = duckdb.connect(str(DB), read_only=True)
    df = con.sql("select * from mart_diesel__item_region_week").df()
    con.close()

    # Keep items seen in BOTH regions, both before and after the policy.
    # Other items can't be compared across regions, so they add nothing.
    cover = df.groupby("item_id").agg(
        pen_pre=("is_peninsular", lambda s: bool((s & ~df.loc[s.index, "is_post"]).any())),
        pen_post=("is_peninsular", lambda s: bool((s & df.loc[s.index, "is_post"]).any())),
        east_pre=("is_peninsular", lambda s: bool((~s & ~df.loc[s.index, "is_post"]).any())),
        east_post=("is_peninsular", lambda s: bool((~s & df.loc[s.index, "is_post"]).any())),
    )
    keep = cover[cover.all(axis=1)].index
    df = df[df.item_id.isin(keep)].copy()

    # Fixed-effect labels and model variables.
    df["peninsular"] = df.is_peninsular.astype(int)
    df["post"] = df.is_post.astype(int)
    df["treat_post"] = df.peninsular * df.post
    df["week_id"] = df.week_start.astype(str)
    df["item_region"] = df.item_id.astype(str) + "_" + df.region
    df["item_week"] = df.item_id.astype(str) + "_" + df.week_id
    df["event_bin"] = df.event_week.clip(-BIN_LIMIT, BIN_LIMIT).astype(int)
    return df


def plot_raw_trends(df: pd.DataFrame) -> None:
    """Average price change vs each pair's own pre-policy level, by region and week."""
    trend = df.groupby(["week_start", "region"]).y.mean().unstack() * 100
    fig, ax = plt.subplots(figsize=(10, 4.5))
    for region, colour in [("Peninsular", "#c0392b"), ("East", "#2471a3")]:
        ax.plot(trend.index, trend[region], label=region, color=colour, lw=1.6)
    ax.axvline(pd.Timestamp("2024-06-10"), color="grey", ls="--", lw=1)
    ax.text(pd.Timestamp("2024-06-17"), ax.get_ylim()[1] * 0.92, "Diesel RM3.35 in Peninsula", fontsize=9)
    ax.axhline(0, color="black", lw=0.6)
    ax.set_ylabel("% vs own pre-June-2024 level")
    ax.set_title("Grocery price change by region (average across items)")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(OUT / "raw_trends.png", dpi=150)
    plt.close(fig)


def event_study(df: pd.DataFrame) -> pd.DataFrame:
    """y = item-region effect + item-week effect + sum_k beta_k * Peninsular * [week = k].
    The item-week effect absorbs anything that moved an item's price nationwide in a
    given week, so each beta_k is the Peninsular-minus-East gap in week k, relative
    to the week before the policy (k = -1)."""
    fit = pf.feols(
        "y ~ i(event_bin, peninsular, ref=-1) | item_region + item_week",
        data=df,
        vcov=VCOV,
    )
    est = fit.tidy().reset_index()
    est["event_week"] = est["Coefficient"].map(week_of)
    est = est.rename(columns={"Estimate": "coef", "Std. Error": "se", "2.5%": "ci_low", "97.5%": "ci_high"})
    est = est[["event_week", "coef", "se", "ci_low", "ci_high"]]
    ref = pd.DataFrame({"event_week": [-1], "coef": [0.0], "se": [0.0], "ci_low": [0.0], "ci_high": [0.0]})
    est = pd.concat([est, ref]).sort_values("event_week").reset_index(drop=True)
    for c in ["coef", "ci_low", "ci_high"]:
        est[c + "_pct"] = 100 * (np.exp(est[c]) - 1)

    # Joint test: are ALL pre-policy coefficients zero? (parallel pre-trends)
    names = list(fit.coef().index)
    pre_idx = [i for i, n in enumerate(names) if week_of(n) < -1]
    R = np.zeros((len(pre_idx), len(names)))
    for row, j in enumerate(pre_idx):
        R[row, j] = 1
    wald = fit.wald_test(R=R, distribution="chi2")
    print("\nPre-trend check (joint test that all pre-policy weeks equal zero):")
    print(f"  chi-squared = {float(wald['statistic']):.2f} on {len(pre_idx)} coefficients, "
          f"p-value = {float(wald['pvalue']):.3f}  (a large p-value = no evidence of different pre-trends)")
    pre = est[(est.event_week < -1)]
    print(f"  Average pre-policy gap: {pre.coef_pct.mean():+.2f}%  "
          f"(largest absolute: {pre.coef_pct.abs().max():.2f}%)")
    return est


def plot_event_study(est: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.fill_between(est.event_week, est.ci_low_pct, est.ci_high_pct, color="#c0392b", alpha=0.18, lw=0)
    ax.plot(est.event_week, est.coef_pct, color="#c0392b", lw=1.5, marker="o", ms=2.5)
    ax.axhline(0, color="black", lw=0.6)
    ax.axvline(-0.5, color="grey", ls="--", lw=1)
    ax.set_xlabel(f"Weeks since 10 June 2024 (end points group all weeks beyond +/-{BIN_LIMIT})")
    ax.set_ylabel("Peninsular minus East (%)")
    ax.set_title("Event study: grocery prices in Peninsular vs East Malaysia, same item, same week (95% CI)")
    fig.tight_layout()
    fig.savefig(OUT / "event_study.png", dpi=150)
    plt.close(fig)


def did(df: pd.DataFrame, weights: str | None = None) -> None:
    fit = pf.feols(
        "y ~ treat_post | item_region + item_week",
        data=df,
        weights=weights,
        vcov=VCOV,
    )
    b, (lo, hi) = fit.coef()["treat_post"], fit.confint().loc["treat_post"].values
    pct = lambda x: 100 * (np.exp(x) - 1)
    label = "weighted by number of shops" if weights else "each item counts equally"
    print(f"  DiD ({label}): {pct(b):+.2f}%  [95% CI {pct(lo):+.2f}% to {pct(hi):+.2f}%], "
          f"p = {fit.pvalue()['treat_post']:.3f}")


def main() -> None:
    OUT.mkdir(exist_ok=True)
    df = load_panel()
    print(f"Panel: {len(df):,} item-region-week cells, {df.item_id.nunique()} items, "
          f"{df.week_id.nunique()} weeks, {int(df.n_pairs.sum()):,} premise-item-week observations")

    plot_raw_trends(df)
    est = event_study(df)
    est.to_csv(OUT / "event_study_coefs.csv", index=False)
    plot_event_study(est)

    print("\nDifference-in-differences: extra price change in the Peninsula after 10 June 2024")
    did(df)
    did(df, weights="n_pairs")
    print(f"\nSaved: {OUT/'raw_trends.png'}, {OUT/'event_study.png'}, {OUT/'event_study_coefs.csv'}")


if __name__ == "__main__":
    main()
