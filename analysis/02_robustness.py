"""
Step 3b: robustness checks for the diesel analysis.

Step 3a found that pre-trends were not parallel and that the overall DiD was
slightly NEGATIVE. This script asks whether that result survives three fixes,
and how big the background "noise" is:

  A. Better baseline   : compare with the 5 weeks BEFORE the policy was announced
                         (weeks -8 to -4), not the single week before the change.
                         Weeks -3 to -1 fall after the late-May announcement and are
                         shown separately as an "anticipation" window.
  B. Seasonal fix      : year-over-year changes (each week vs the same week a year
                         earlier) remove festivals that differ by region.
  C. Short window      : 9 weeks before vs 13 weeks after the change, so later
                         unrelated shocks (e.g. early 2025) can't leak in.
  D. Placebo dates     : the same short-window DiD at 12 fake dates in 2023-24.
                         How big are "effects" when nothing happened? That is our
                         noise level.
  E. Where             : short-window DiD by item category and by shop type.
  F. Diagnosis         : which categories and East states drive the gap that opens
                         from February 2025.

Run from the project root:  python analysis/02_robustness.py
Outputs go to outputs/ (charts and CSVs); key numbers are printed.
"""

import re
import warnings
from pathlib import Path

import duckdb
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyfixest as pf

# pyfixest warns when it drops item-weeks seen in only one region. Those rows
# can't be compared across regions anyway, so the warning is expected here.
warnings.filterwarnings("ignore", message=".*singleton fixed effect.*")
warnings.filterwarnings("ignore", message=".*Distribution changed to chi2.*")

DB = Path("warehouse/pump_to_pasar.duckdb")
OUT = Path("outputs")
VCOV = {"CRV1": "item_id"}       # standard errors clustered by item
BASE = (-8, -4)                  # pre-announcement baseline weeks
ANTICIPATION = (-3, -1)          # after the late-May 2024 announcement, before 10 June
SHORT_PRE, SHORT_POST = (-12, -4), (0, 12)   # short window (anticipation excluded)
PLACEBO_DATES = list(range(-60, -15, 4))     # fake policy weeks, all fully pre-policy


pct = lambda x: 100 * (np.exp(x) - 1)


# ---------------------------------------------------------------- data
def add_labels(df: pd.DataFrame, group: str = "region") -> pd.DataFrame:
    df = df.copy()
    df["peninsular"] = df.is_peninsular.astype(int)
    df["week_id"] = df.week_start.astype(str)
    df["item_region"] = df.item_id.astype(str) + "_" + df[group].astype(str)
    df["item_week"] = df.item_id.astype(str) + "_" + df.week_id
    return df


def both_regions(df: pd.DataFrame) -> pd.DataFrame:
    """Keep items observed in both regions, both before and after the policy."""
    cells = df.groupby(["item_id", "region", "is_post"]).size().unstack(["region", "is_post"])
    keep = cells.dropna().index
    return df[df.item_id.isin(keep)]


def load(table: str) -> pd.DataFrame:
    con = duckdb.connect(str(DB), read_only=True)
    df = con.sql(f"select * from {table}").df()
    con.close()
    return df


# ---------------------------------------------------------------- models
def event_study(df: pd.DataFrame, outcome: str, lo: int, hi: int) -> tuple[pd.DataFrame, dict]:
    """Event study relative to the pooled baseline weeks BASE (shown as 0)."""
    d = df[df.event_week.between(lo, hi)].copy()
    d["ev"] = d.event_week.where(~d.event_week.between(*BASE), -100)   # -100 = baseline
    fit = pf.feols(f"{outcome} ~ i(ev, peninsular, ref=-100) | item_region + item_week",
                   data=d, vcov=VCOV)
    t = fit.tidy().reset_index()
    t["event_week"] = t.Coefficient.map(lambda s: int(re.search(r"::(-?\d+):", s).group(1)))
    t = t.rename(columns={"Estimate": "coef", "2.5%": "ci_low", "97.5%": "ci_high"})
    for c in ["coef", "ci_low", "ci_high"]:
        t[c + "_pct"] = pct(t[c])
    t = t[["event_week", "coef_pct", "ci_low_pct", "ci_high_pct"]]
    base_rows = pd.DataFrame({"event_week": range(BASE[0], BASE[1] + 1),
                              "coef_pct": 0.0, "ci_low_pct": 0.0, "ci_high_pct": 0.0})
    t = pd.concat([t, base_rows]).sort_values("event_week").reset_index(drop=True)

    # Pre-trend test on the weeks before the baseline (anticipation excluded)
    names = list(fit.coef().index)
    idx = [i for i, n in enumerate(names) if int(re.search(r"::(-?\d+):", n).group(1)) < BASE[0]]
    R = np.eye(len(names))[idx]
    w = fit.wald_test(R=R, distribution="chi2")
    pre = t[t.event_week < BASE[0]]
    stats = {"pretrend_p": float(w["pvalue"]), "n_pre": len(idx),
             "pre_mean_pct": pre.coef_pct.mean(), "pre_sd_pct": pre.coef_pct.std(),
             "pre_max_abs_pct": pre.coef_pct.abs().max()}
    return t, stats


def window_did(df: pd.DataFrame, outcome: str, centre: int) -> dict:
    """Short-window DiD around `centre`: weeks centre-12..centre-4 vs centre..centre+12."""
    rel = df.event_week - centre
    d = df[rel.between(*SHORT_PRE) | rel.between(*SHORT_POST)].copy()
    d["treat_post"] = d.peninsular * (rel[d.index] >= 0).astype(int)
    fit = pf.feols(f"{outcome} ~ treat_post | item_region + item_week", data=d, vcov=VCOV)
    b = fit.coef()["treat_post"]
    lo, hi = fit.confint().loc["treat_post"].values
    return {"centre_week": centre, "did_pct": pct(b), "ci_low_pct": pct(lo), "ci_high_pct": pct(hi),
            "p": fit.pvalue()["treat_post"], "items": d.item_id.nunique()}


def yoy_panel(df: pd.DataFrame) -> pd.DataFrame:
    """Each item-region-week minus the same item-region 52 weeks earlier.
    Only uses pre-policy weeks as the 'year earlier' base (event weeks -23 to 51)."""
    prev = df[["item_id", "region", "event_week", "y"]].copy()
    prev["event_week"] += 52
    out = df.merge(prev, on=["item_id", "region", "event_week"], suffixes=("", "_ly"))
    out["y_yoy"] = out.y - out.y_ly
    return out[out.event_week.between(-23, 51)]


# ---------------------------------------------------------------- charts
def plot_es(t: pd.DataFrame, title: str, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.axvspan(BASE[0] - 0.5, BASE[1] + 0.5, color="grey", alpha=0.12, label="Baseline (weeks -8 to -4)")
    ax.axvspan(ANTICIPATION[0] - 0.5, ANTICIPATION[1] + 0.5, color="#f5b041", alpha=0.25,
               label="After announcement, before change")
    ax.fill_between(t.event_week, t.ci_low_pct, t.ci_high_pct, color="#c0392b", alpha=0.18, lw=0)
    ax.plot(t.event_week, t.coef_pct, color="#c0392b", lw=1.4, marker="o", ms=2.5)
    ax.axhline(0, color="black", lw=0.6)
    ax.axvline(-0.5, color="grey", ls="--", lw=1)
    ax.set_xlabel("Weeks since 10 June 2024")
    ax.set_ylabel("Peninsular minus East (%)")
    ax.set_title(title)
    ax.legend(frameon=False, fontsize=8, loc="lower left")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def plot_placebo(placebo: pd.DataFrame, real: dict, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.errorbar(placebo.centre_week, placebo.did_pct,
                yerr=[placebo.did_pct - placebo.ci_low_pct, placebo.ci_high_pct - placebo.did_pct],
                fmt="o", color="#7f8c8d", capsize=2, label="Fake policy dates (nothing happened)")
    ax.errorbar([0], [real["did_pct"]],
                yerr=[[real["did_pct"] - real["ci_low_pct"]], [real["ci_high_pct"] - real["did_pct"]]],
                fmt="o", color="#c0392b", capsize=3, ms=7, label="Real date: 10 June 2024")
    ax.axhline(0, color="black", lw=0.6)
    ax.set_xlabel("Policy week tested (0 = 10 June 2024)")
    ax.set_ylabel("Short-window DiD (%)")
    ax.set_title("Placebo test: is the real estimate bigger than the background noise?")
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


# ---------------------------------------------------------------- main
def main() -> None:
    OUT.mkdir(exist_ok=True)
    summary = []

    df = add_labels(both_regions(load("mart_diesel__item_region_week")))
    print(f"Panel: {len(df):,} cells, {df.item_id.nunique()} items, {df.week_id.nunique()} weeks")

    # A. Event study with the pre-announcement baseline
    t_a, s_a = event_study(df, "y", -52, 52)
    t_a.to_csv(OUT / "es_baseline_fix.csv", index=False)
    plot_es(t_a, "A. Event study vs pre-announcement baseline (95% CI)", OUT / "es_baseline_fix.png")
    print("\nA. Event study vs weeks -8 to -4")
    print(f"   Pre-trend test (weeks -52 to -9): p = {s_a['pretrend_p']:.3f}; "
          f"pre-policy gaps average {s_a['pre_mean_pct']:+.2f}%, typical swing (SD) {s_a['pre_sd_pct']:.2f}%, "
          f"largest {s_a['pre_max_abs_pct']:.2f}%")
    for lo, hi, label in [(-3, -1, "after announcement (-3 to -1)"), (0, 12, "first 3 months (0 to 12)"),
                          (13, 34, "months 4-8 (13 to 34)"), (35, 52, "from Feb 2025 (35 to 52)")]:
        m = t_a[t_a.event_week.between(lo, hi)].coef_pct.mean()
        print(f"   Average gap, {label:32s}: {m:+.2f}%")
        summary.append({"check": f"A gap {label}", "value_pct": m})

    # B. Year-over-year version
    yoy = add_labels(yoy_panel(df))
    t_b, s_b = event_study(yoy, "y_yoy", -23, 51)
    t_b.to_csv(OUT / "es_yoy.csv", index=False)
    plot_es(t_b, "B. Event study, year-over-year changes (removes regional festivals) (95% CI)",
            OUT / "es_yoy.png")
    print("\nB. Year-over-year event study (weeks -23 to 51)")
    print(f"   Pre-trend test (weeks -23 to -9): p = {s_b['pretrend_p']:.3f}; "
          f"typical pre-policy swing (SD) {s_b['pre_sd_pct']:.2f}%")
    for lo, hi, label in [(0, 12, "first 3 months"), (13, 34, "months 4-8"), (35, 51, "from Feb 2025")]:
        m = t_b[t_b.event_week.between(lo, hi)].coef_pct.mean()
        print(f"   Average gap, {label:16s}: {m:+.2f}%")
        summary.append({"check": f"B yoy gap {label}", "value_pct": m})

    # C. Short-window DiD at the real date
    real = window_did(df, "y", 0)
    real_yoy = window_did(yoy, "y_yoy", 0)
    print("\nC. Short-window DiD (weeks -12 to -4 vs 0 to 12)")
    for name, r in [("levels", real), ("year-over-year", real_yoy)]:
        print(f"   {name:15s}: {r['did_pct']:+.2f}%  [95% CI {r['ci_low_pct']:+.2f}% to {r['ci_high_pct']:+.2f}%], "
              f"p = {r['p']:.3f}")
        summary.append({"check": f"C short-window DiD {name}", "value_pct": r["did_pct"],
                        "ci_low_pct": r["ci_low_pct"], "ci_high_pct": r["ci_high_pct"], "p": r["p"]})

    # D. Placebo dates
    placebo = pd.DataFrame([window_did(df, "y", c) for c in PLACEBO_DATES])
    placebo.to_csv(OUT / "placebo.csv", index=False)
    plot_placebo(placebo, real, OUT / "placebo.png")
    share = (placebo.did_pct.abs() >= abs(real["did_pct"])).mean()
    print(f"\nD. Placebo test ({len(placebo)} fake dates, all before the policy)")
    print(f"   Fake-date 'effects' range {placebo.did_pct.min():+.2f}% to {placebo.did_pct.max():+.2f}% "
          f"(SD {placebo.did_pct.std():.2f}%)")
    print(f"   Share of fake dates with an effect at least as large as the real one: {share:.0%}")
    summary.append({"check": "D placebo SD", "value_pct": placebo.did_pct.std()})
    summary.append({"check": "D share of placebos >= real (abs)", "value_pct": 100 * share})

    # E1. By item category (short window)
    rows = []
    for cat, g in df.groupby("item_category"):
        if g.item_id.nunique() >= 5 and cat != "UNMAPPED":
            r = window_did(g, "y", 0)
            r["category"] = cat
            rows.append(r)
    by_cat = pd.DataFrame(rows).sort_values("did_pct", ascending=False)
    by_cat.to_csv(OUT / "did_by_category.csv", index=False)
    print("\nE1. Short-window DiD by item category (categories with 5+ items)")
    print(by_cat[["category", "items", "did_pct", "ci_low_pct", "ci_high_pct", "p"]]
          .round(2).to_string(index=False))

    # E2. By shop type (short window)
    typ = load("mart_diesel__item_region_type_week")
    rows = []
    for ptype, g in typ.groupby("premise_type"):
        g = both_regions(g)
        if g.item_id.nunique() >= 20:
            r = window_did(add_labels(g), "y", 0)
            r["premise_type"] = ptype
            rows.append(r)
    by_type = pd.DataFrame(rows).sort_values("did_pct", ascending=False)
    by_type.to_csv(OUT / "did_by_premise_type.csv", index=False)
    print("\nE2. Short-window DiD by shop type")
    print(by_type[["premise_type", "items", "did_pct", "ci_low_pct", "ci_high_pct", "p"]]
          .round(2).to_string(index=False))

    # F. What drives the gap from February 2025?
    wide = df.pivot_table(index=["item_id", "item_category", "event_week"], columns="region", values="y").dropna()
    wide["gap"] = wide.Peninsular - wide.East
    wide = wide.reset_index()
    early = wide[wide.event_week.between(0, 34)].groupby(["item_id", "item_category"]).gap.mean()
    late = wide[wide.event_week.between(35, 52)].groupby(["item_id", "item_category"]).gap.mean()
    chg = (late - early).dropna().reset_index(name="change")
    n_items = len(chg)
    contrib = (chg.groupby("item_category").change
               .agg(items="size", avg_change="mean", total="sum")
               .assign(share_of_shift=lambda x: x.total / chg.change.sum() * 100)
               .sort_values("total"))
    contrib["avg_change_pct"] = pct(contrib.avg_change)
    contrib.round(3).to_csv(OUT / "feb2025_gap_by_category.csv")
    print(f"\nF1. Change in Peninsular-minus-East gap, weeks 35-52 vs 0-34 ({n_items} items)")
    print(f"   Overall: {pct(chg.change.mean()):+.2f}%. Categories pushing it most negative:")
    print(contrib.head(8)[["items", "avg_change_pct", "share_of_shift"]].round(1).to_string())

    con = duckdb.connect(str(DB), read_only=True)
    states = con.sql("""
        select coalesce(region, '?') as region, state,
               avg(log_price_vs_pre) filter (where event_week between 0 and 34)  as early,
               avg(log_price_vs_pre) filter (where event_week between 35 and 52) as late
        from mart_diesel__pair_week
        group by 1, 2
    """).df()
    con.close()
    states["change_pct"] = pct(states.late - states.early)
    states = states.sort_values(["region", "change_pct"], ascending=[True, False])
    print("\nF2. Average price change from early to late post-period, by state")
    print(states[["region", "state", "change_pct"]].round(2).to_string(index=False))

    pd.DataFrame(summary).round(3).to_csv(OUT / "robustness_summary.csv", index=False)
    print("\nSaved charts: es_baseline_fix.png, es_yoy.png, placebo.png; tables: *.csv in outputs/")


if __name__ == "__main__":
    main()
