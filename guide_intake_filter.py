"""
guide_intake_filter -- Part 5: upgrade the fixed ACTION_FLOOR guide gate to a fitted
HistGradientBoosting meta-model (the LightGBM/XGBoost idea; sklearn's HGB is the
drop-in equivalent already installed here), and MEASURE whether it beats the rule.

It answers one concrete question: at the SAME recall (>=0.95) of keeping every guide
that would actually yield a grounded step, how many junk guides can we now REJECT
(i.e. how many wasted LLM calls does the autonomous pipeline save)?

Trained on the p6 telemetry (guide features -> did it produce >=1 grounded step), with an
APP-LEVEL train/test split so no app leaks across folds. Emits fig8 + metrics json.

Usage: python guide_intake_filter.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score, average_precision_score, precision_recall_curve

import ml_data_science_report as M   # reuse the exact feature/label builder
import decompose_guides as d

OUT = Path("reports/ml_analysis")
OUT.mkdir(parents=True, exist_ok=True)

FEATURES = ["action_score", "gui_density", "uniq_widgets", "word_count", "cli_score"]


def p(m):
    print(f"[filter] {m}", flush=True)


def build_xy(rows):
    # only rows with a KNOWN outcome (a trajectory file was written) have a trustworthy label
    known = [r for r in rows if r["has_file"]]
    X = np.array([[r[f] for f in FEATURES] for r in known], dtype=float)
    y = np.array([1 if r["grounded"] >= 1 else 0 for r in known], dtype=int)
    apps = np.array([r["app_key"] for r in known])
    return X, y, apps, known


def operating_point(recall_target, y_true, score):
    """Highest-precision threshold whose recall >= recall_target."""
    prec, rec, thr = precision_recall_curve(y_true, score)
    best = None
    for i in range(len(rec) - 1):
        if rec[i] >= recall_target:
            if best is None or prec[i] > best[0]:
                best = (prec[i], rec[i], thr[i])
    return best  # (precision, recall, threshold) or None


def rule_score(rows):
    # the CURRENT gate: is_desktop_gui AND action_score >= ACTION_FLOOR  -> binary keep
    return np.array([1.0 if r["attempted"] else 0.0 for r in rows], dtype=float)


def main():
    p("rebuilding feature/label table from corpus telemetry...")
    rows = M.build_dataset()
    X, y, apps, known = build_xy(rows)
    p(f"{len(known)} guides with known outcomes; positive rate={y.mean():.3f}")

    tr_app, te_app = train_test_split(list(dict.fromkeys(apps)), test_size=.3, random_state=7)
    tr = np.isin(apps, tr_app); te = np.isin(apps, te_app)
    yt = y[te]

    lg = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000)).fit(X[tr], y[tr])
    gb = HistGradientBoostingClassifier(max_iter=300, learning_rate=.06,
                                        max_depth=4, random_state=7).fit(X[tr], y[tr])
    p_lg = lg.predict_proba(X[te])[:, 1]
    p_gb = gb.predict_proba(X[te])[:, 1]

    # current fixed-rule gate evaluated on the SAME held-out rows
    rule_known = np.array([1.0 if r["attempted"] else 0.0 for r in known])
    rule_te = rule_known[te]

    def rule_pr(y_true, keep):
        keep = keep.astype(bool)
        tp = int(((keep) & (y_true == 1)).sum()); fp = int(((keep) & (y_true == 0)).sum())
        fn = int(((~keep) & (y_true == 1)).sum())
        prec = tp / max(1, tp + fp); rec = tp / max(1, tp + fn)
        return prec, rec, keep.mean()

    r_prec, r_rec, r_keep = rule_pr(yt, rule_te)
    o_lg = operating_point(.95, yt, p_lg)
    o_gb = operating_point(.95, yt, p_gb)

    auc_lg = roc_auc_score(yt, p_lg); auc_gb = roc_auc_score(yt, p_gb)
    ap_lg = average_precision_score(yt, p_lg); ap_gb = average_precision_score(yt, p_gb)

    # fig8
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.2))
    for sc, lbl, col in [(p_lg, f"Logistic (AUC={auc_lg:.3f})", "#1971c2"),
                          (p_gb, f"HistGradientBoost (AUC={auc_gb:.3f})", "#e8590c")]:
        fpr, tpr, _ = __import__("sklearn.metrics", fromlist=["roc_curve"]).roc_curve(yt, sc)
        ax1.plot(fpr, tpr, color=col, lw=2, label=lbl)
    ax1.plot([0, 1], [0, 1], "k--", alpha=.5)
    ax1.set_title("Held-out ROC — guide yields >=1 grounded step", weight="bold")
    ax1.set_xlabel("FPR"); ax1.set_ylabel("TPR"); ax1.grid(alpha=.3); ax1.legend()

    names = ["ACTION_FLOOR\nrule", "Logistic", "HistGB"]
    precs = [r_prec, o_lg[0] if o_lg else 0, o_gb[0] if o_gb else 0]
    keeps = [r_keep, None, None]
    # fraction of guides still sent to the model at recall>=0.95 (lower = fewer wasted calls)
    def keep_frac_at_recall(score):
        prec, rec, thr = precision_recall_curve(yt, score)
        for i in range(len(rec) - 1):
            if rec[i] >= .95:
                thr_i = thr[i]
                return float((score >= thr_i).mean())
        return 1.0
    keeps = [r_keep, keep_frac_at_recall(p_lg), keep_frac_at_recall(p_gb)]
    x = np.arange(3)
    b1 = ax2.bar(x - .18, precs, .36, color="#2b8a3e", label="precision @ recall>=.95")
    b2 = ax2.bar(x + .18, keeps, .36, color="#868e96", label="share of guides still run")
    for b in list(b1) + list(b2):
        ax2.text(b.get_x() + b.get_width() / 2, b.get_height() + .01, f"{b.get_height():.2f}",
                 ha="center", fontsize=8)
    ax2.set_xticks(x); ax2.set_xticklabels(names); ax2.set_ylim(0, 1.1)
    ax2.set_title("At recall>=0.95: precision up, wasted calls down", weight="bold")
    ax2.grid(alpha=.3, axis="y"); ax2.legend(fontsize=8)
    fig.suptitle("Part 5 — learned guide-intake filter vs the fixed ACTION_FLOOR gate", y=1.02, weight="bold")
    fig.tight_layout()
    fig.savefig(OUT / "fig8_intake_filter.png", dpi=120, bbox_inches="tight")
    plt.close(fig)

    metrics = {"n_known": int(len(known)), "pos_rate": round(float(y.mean()), 3),
               "heldout_apps": int(len(te_app)),
               "logistic": {"auc": round(auc_lg, 3), "pr_auc": round(ap_lg, 3),
                            "precision@r95": round(o_lg[0], 3) if o_lg else None},
               "histgb": {"auc": round(auc_gb, 3), "pr_auc": round(ap_gb, 3),
                          "precision@r95": round(o_gb[0], 3) if o_gb else None},
               "action_floor_rule": {"precision": round(r_prec, 3), "recall": round(r_rec, 3),
                                     "share_run": round(r_keep, 3)},
               "share_run_at_r95": {"rule": round(r_keep, 3),
                                    "logistic": round(keep_frac_at_recall(p_lg), 3),
                                    "histgb": round(keep_frac_at_recall(p_gb), 3)}}
    (OUT / "intake_filter_metrics.json").write_text(json.dumps(metrics, indent=3), encoding="utf-8")
    p("=" * 60)
    p(f"held-out AUC   : logistic {auc_lg:.3f}  ->  HistGB {auc_gb:.3f}")
    p(f"held-out PR-AUC: logistic {ap_lg:.3f}  ->  HistGB {ap_gb:.3f}")
    p(f"precision@recall>=.95 : rule {r_prec:.3f} | logistic {o_lg[0] if o_lg else float('nan'):.3f} | HistGB {o_gb[0] if o_gb else float('nan'):.3f}")
    p(f"guides still run@r.95 : rule {r_keep:.3f} | logistic {keep_frac_at_recall(p_lg):.3f} | HistGB {keep_frac_at_recall(p_gb):.3f}")
    p("figure -> reports/ml_analysis/fig8_intake_filter.png")


if __name__ == "__main__":
    main()
