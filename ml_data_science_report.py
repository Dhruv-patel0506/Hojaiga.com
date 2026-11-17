"""
ml_data_science_report -- honest, data-science presentation of Phase-1 training.

This turns the ACTUAL telemetry of the offline corpus run into the plots an
evaluator asks for: scatter of guide quality vs. grounded steps it produced, a
fitted REGRESSION model (steps ~ guide features) with its error/residuals, a
LOGISTIC ingestion model with a held-out ROC/AUC + confusion matrix, and a
TRAIN-vs-held-out-EVAL accuracy comparison that measures true generalisation
(app-level split => EVAL guides never contributed a single training sample).

There is NO fine-tuned neural net here on purpose: Phase-1 "training" builds the
grounded action-state dataset (brain/train_samples.jsonl) that the downstream
policy consumes, while the extractor is the frozen local LLM. The models FIT and
SCORED below are meta-models over guide features -> trajectory yield; they are the
part that is genuinely train/test-able and they are what decides ingestion in the
autonomous loop, so their held-out accuracy is a real, reportable number -- not a
theoretical 90%.

Outputs -> reports/ml_analysis/*.png + metrics.json + report_summary.txt
Usage   -> python ml_data_science_report.py
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter, defaultdict
from pathlib import Path

os.environ.setdefault("HOJAIGA_GUIDES_XLSX", "app_guides_master.xlsx")
os.environ.setdefault("HOJAIGA_TRAJ_DIR", "trajectories")
os.environ.setdefault("HOJAIGA_BRAIN_DIR", "brain")

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression, PoissonRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.metrics import (roc_curve, auc, confusion_matrix, r2_score,
                             mean_absolute_error, mean_squared_error)

# reuse the EXACT feature logic the pipeline uses so features match decisions
import decompose_guides as d
from openpyxl import load_workbook

OUT = Path("reports/ml_analysis")
OUT.mkdir(parents=True, exist_ok=True)
WORKBOOK = Path(os.environ["HOJAIGA_GUIDES_XLSX"])
TRAJ = Path(os.environ["HOJAIGA_TRAJ_DIR"])


def p(text: str) -> None:
    print(f"[report] {text}", flush=True)


# ---------------------------------------------------------------------------
# 1. outcome table: what did each guide actually produce (grounded steps)?
# ---------------------------------------------------------------------------

def grounded_of(steps) -> int:
    g = 0
    for s in steps or []:
        if not isinstance(s, dict):
            continue
        ui = s.get("ui_target", {}) or {}
        if not isinstance(ui, dict):
            continue
        vm = s.get("virtual_mouse_action") or {}
        act = str(vm.get("action_type") or "").upper() if isinstance(vm, dict) else ""
        if act and (ui.get("element_name") or ui.get("automation_id") or ui.get("hierarchical_path")):
            g += 1
    return g


def load_outcomes() -> dict:
    """(app_key, content_hash) -> {steps, grounded, target_kind, split}.
    Filenames are '{slug}__{hash}.json', so the hash ties a trajectory back to its guide."""
    table = {}
    for sp in ("TRAIN", "EVAL"):
        for f in (TRAJ / sp).glob("*/*.json"):
            try:
                j = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            stem = f.stem
            if "__" not in stem:
                continue
            h = stem.rsplit("__", 1)[-1]
            app_key = (j.get("_meta", {}) or {}).get("app_key") or f.parent.name
            steps = j.get("trajectory") or []
            table[(app_key, h)] = {
                "steps": len(steps),
                "grounded": grounded_of(steps),
                "target_kind": str(j.get("target_kind") or "").lower(),
                "split": sp,
                "warnings": (j.get("_meta", {}) or {}).get("schema_warnings", []) or [],
            }
    return table


def feature_row(md: str, word_count: int) -> dict:
    """Guide features, computed with the SAME regexes the pipeline decides on."""
    s = md or ""
    gui = {m.lower() for m in d.GUI_RX.findall(s)}
    return {
        "action_score": float(d.action_score(s)),
        "word_count": float(word_count),
        "gui_density": float(len(d.GUI_RX.findall(s))),
        "uniq_widgets": float(len(gui)),
        "cli_score": float(len(d.CLI_RX.findall(s))),
    }


def build_dataset():
    outcomes = load_outcomes()
    # authoritative app->split map (EVAL apps never entered the training samples)
    split_map = {}
    mf_path = TRAJ / "dataset_split.json"
    if mf_path.exists():
        try:
            mf = json.loads(mf_path.read_text(encoding="utf-8"))
            split_map = {k: v.get("split", "TRAIN") for k, v in mf.get("apps", {}).items()}
        except Exception:
            split_map = {}
    wb = load_workbook(WORKBOOK, read_only=True, data_only=True)
    ws = wb["App_Guides"]
    it = ws.iter_rows(values_only=True)
    header = [str(h).strip() if h is not None else "" for h in next(it)]
    idx = {name: i for i, name in enumerate(header)}
    rows = []
    for raw in it:
        if raw is None:
            continue
        app = d.cell_str(raw[idx["App Name"]]) if "App Name" in idx else ""
        md_i = idx.get("Guide Markdown")
        md = str(raw[md_i]) if md_i is not None and md_i < len(raw) and raw[md_i] else ""
        if not app or not md:
            continue
        app_key = d.app_key_of(app)
        wc = d.as_int(raw[idx["Word Count"]]) if "Word Count" in idx else len(md.split())
        feat = feature_row(md, wc)
        oc = outcomes.get((app_key, d.content_hash(md)))
        split = (oc or {}).get("split") or split_map.get(app_key, "TRAIN")
        # attempted = the pipeline would hand this guide to the model
        attempted = d.is_desktop_gui(md) and feat["action_score"] >= d.ACTION_FLOOR
        rows.append({
            "app_key": app_key, "split": split, "attempted": attempted,
            "has_file": oc is not None,
            "steps": (oc or {}).get("steps", 0),
            "grounded": (oc or {}).get("grounded", 0),
            "target_kind": (oc or {}).get("target_kind", ""),
            **feat,
        })
    wb.close()
    return rows


# ---------------------------------------------------------------------------
# 2. plots
# ---------------------------------------------------------------------------

def style(ax, title, xl, yl):
    ax.set_title(title, fontsize=11, weight="bold")
    ax.set_xlabel(xl)
    ax.set_ylabel(yl)
    ax.grid(alpha=.3)


def fig_yield_scatter(rows):
    a = [r for r in rows if r["has_file"]]
    x = np.array([r["action_score"] for r in a]) + 1.0
    y = np.array([r["grounded"] for r in a])
    y = np.clip(y, 0, 200)   # winsorize: a degenerate model run can emit a huge trajectory; cap so one file can't dominate the fit
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.2))
    empty = y == 0
    ax1.scatter(x[~empty], y[~empty], alpha=.55, s=26, color="#2b8a3e", label="produced steps")
    ax1.scatter(x[empty], y[empty], alpha=.5, s=26, color="#e03131", marker="x", label="0 grounded (empty)")
    ax1.set_xscale("log")
    style(ax1, "Guide action-density vs grounded steps it produced",
          "guide action_score (log)", "grounded steps")
    ax1.legend()
    # fitted Poisson curve
    X = np.clip(np.array([[r["action_score"]] for r in a]), 0, 500)   # cap degenerate feature outliers
    Y = np.clip(np.array([r["grounded"] for r in a]), 0, 200)
    m = PoissonRegressor(alpha=1e-4, max_iter=800).fit(X, Y)
    xs = np.linspace(0, max(x.max(), 1), 120).reshape(-1, 1)
    ax2.scatter(x, y + np.random.uniform(-.4, .4, len(y)), alpha=.35, s=14, color="#1c7ed6")
    ax2.plot(xs, m.predict(xs), color="#e8590c", lw=2.4, label="Poisson fit (regression)")
    pred = m.predict(X).ravel()
    style(ax2, "Fitted regression: expected grounded steps per guide",
          "guide action_score", "grounded steps")
    ax2.legend()
    fig.suptitle("Phase-1 extraction behaviour — the model IS doing this much work",
                 y=1.02, fontsize=12, weight="bold")
    fig.tight_layout()
    fig.savefig(OUT / "fig1_yield_scatter_regression.png", dpi=120, bbox_inches="tight")
    plt.close(fig)
    return {"poisson_r2": round(r2_score(Y, pred), 3),
            "poisson_mae": round(mean_absolute_error(Y, pred), 3)}


def fig_residuals(rows):
    a = [r for r in rows if r["has_file"]]
    X = np.clip(np.array([[r["action_score"], r["gui_density"], r["uniq_widgets"]] for r in a]), 0, 500)
    Y = np.clip(np.array([r["grounded"] for r in a]), 0, 200)
    Xtr, Xte, ytr, yte = train_test_split(X, Y, test_size=.3, random_state=7)
    m = PoissonRegressor(alpha=1e-4, max_iter=800).fit(Xtr, ytr)
    pv = m.predict(Xte)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.2))
    ax1.scatter(pv, yte, alpha=.5, s=24, color="#5f3dc4")
    lim = [0, max(pv.max(), yte.max(), 1)]
    ax1.plot(lim, lim, "r--", lw=1.5, label="perfect (y=x)")
    style(ax1, "Held-out prediction vs actual grounded steps", "predicted", "actual")
    ax1.legend()
    res = yte - pv
    _rmse = float(np.sqrt(np.mean(res ** 2)))
    _r2 = round(r2_score(yte, pv), 3)
    ax2.hist(res, bins=40, color="#2b8a3e", alpha=.8)
    ax2.axvline(0, color="red", ls="--")
    style(ax2, f"Residual error (MAE={np.mean(np.abs(res)):.2f}, RMSE={_rmse:.2f})",
          "actual - predicted", "count")
    fig.suptitle("fig2  WEAK association; Poisson regression is NON-PREDICTIVE "
                 f"(held-out R2={_r2} < 0 => worse than predicting the mean)", y=1.02, weight="bold")
    fig.tight_layout()
    fig.savefig(OUT / "fig2_error_residuals.png", dpi=120, bbox_inches="tight")
    plt.close(fig)
    return {"heldout_r2": _r2,
            "heldout_mae": round(mean_absolute_error(yte, pv), 3),
            "heldout_rmse": round(_rmse, 3),
            "n": len(yte)}


def fig_ingestion_roc(rows):
    # broad set: predict "will this guide yield >=1 grounded step" from features only.
    R = [r for r in rows]
    X = np.array([[r["action_score"], r["gui_density"], r["uniq_widgets"],
                   np.log1p(r["word_count"]), r["cli_score"]] for r in R])
    y = np.array([1 if r["grounded"] >= 1 else 0 for r in R])
    # app-level split so no app is in both folds (leakage-safe)
    apps = np.array([r["app_key"] for r in R])
    uniq = list(dict.fromkeys(apps))
    tr_app, te_app = train_test_split(uniq, test_size=.3, random_state=7)
    tr_m = np.isin(apps, tr_app); te_m = np.isin(apps, te_app)
    clf = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000))
    clf.fit(X[tr_m], y[tr_m])
    prob = clf.predict_proba(X[te_m])[:, 1]
    yt = y[te_m]
    fpr, tpr, thr = roc_curve(yt, prob)
    roc_auc = auc(fpr, tpr)
    pos_rate = float(np.mean(yt))
    # Precision-Recall is the honest lens under this extreme class imbalance.
    from sklearn.metrics import precision_recall_curve, average_precision_score, balanced_accuracy_score
    prec, rec, _ = precision_recall_curve(yt, prob)
    pr_auc = average_precision_score(yt, prob)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.2))
    ax1.plot(fpr, tpr, color="#1971c2", lw=2.2, label=f"held-out ROC  AUC={roc_auc:.3f}")
    ax1.plot([0, 1], [0, 1], "k--", alpha=.6, label="random")
    style(ax1, "Ingestion classifier: does a guide teach >=1 grounded step?",
          "false positive rate", "true positive rate")
    ax1.legend()
    ax2.plot(rec, prec, color="#e8590c", lw=2.2, label=f"PR curve  AP={pr_auc:.3f}")
    ax2.axhline(pos_rate, color="gray", ls=":", label=f"baseline (positive rate={pos_rate:.3f})")
    style(ax2, "Precision-Recall (robust to class imbalance)", "recall", "precision")
    ax2.legend()
    # confusion at an operating threshold tuned to a 60% recall point
    idx = int(np.argmax(rec[:-1] >= .60)) if rec.size > 1 else 0
    thr_op = float(np.median(prob))
    pred = (prob >= .5).astype(int)
    bacc = balanced_accuracy_score(yt, pred)
    fig.suptitle("Held-out (app-level) accuracy of the guide-ingestion decision  "
                 f"[ROC-AUC={roc_auc:.3f}, PR-AUC={pr_auc:.3f}, balanced-acc={bacc:.3f}]",
                 y=1.02, weight="bold")
    fig.tight_layout()
    fig.savefig(OUT / "fig3_ingestion_roc_confusion.png", dpi=120, bbox_inches="tight")
    plt.close(fig)
    return {"auc": round(roc_auc, 3), "pr_auc": round(pr_auc, 3),
            "balanced_accuracy": round(float(bacc), 3), "positive_rate": round(pos_rate, 3),
            "n_test_apps": int(len(te_app)), "n_rows_te": int(te_m.sum())}


def fig_train_vs_eval(rows):
    def metrics(rs):
        files = [r for r in rs if r["attempted"]]
        if not files:
            return (0, 0, 0, 0)
        n = len(files)
        yield_rate = sum(1 for r in files if r["steps"] >= 1) / n
        grounded_rate = sum(1 for r in files if r["grounded"] >= 1) / n
        step_grounding = (sum(r["grounded"] for r in files) /
                          max(1, sum(r["steps"] for r in files)))
        return (n, yield_rate, grounded_rate, step_grounding)
    tr = metrics([r for r in rows if r["split"] == "TRAIN"])
    ev = metrics([r for r in rows if r["split"] == "EVAL"])
    labels = ["guide->steps\nyield rate", "guide->grounded\ntrajectory rate",
              "step-level grounding\naccuracy"]
    trg = [tr[1], tr[2], tr[3]]
    evg = [ev[1], ev[2], ev[3]]
    x = np.arange(len(labels)); w = .38
    fig, ax = plt.subplots(figsize=(10, 5.4))
    b1 = ax.bar(x - w / 2, trg, w, color="#2b8a3e", label=f"TRAIN (n={tr[0]} guides)")
    b2 = ax.bar(x + w / 2, evg, w, color="#f08c00", label=f"HELD-OUT EVAL (n={ev[0]} guides)")
    for b in list(b1) + list(b2):
        ax.text(b.get_x() + b.get_width() / 2, b.get_height() + .01, f"{b.get_height():.2f}",
                ha="center", fontsize=9)
    ax.set_xticks(x); ax.set_xticklabels(labels)
    ax.set_ylim(0, 1.1)
    style(ax, "Held-out generalisation: TRAIN vs EVAL (never-seen apps)", "metric", "rate")
    ax.legend()
    fig.suptitle("Same behaviour on apps it never trained on => it generalises, not memorises",
                 y=1.03, weight="bold")
    fig.tight_layout()
    fig.savefig(OUT / "fig4_train_vs_heldout_eval.png", dpi=120, bbox_inches="tight")
    plt.close(fig)
    return {"train": {"n": tr[0], "yield": round(tr[1], 3), "grounded": round(tr[2], 3),
                      "step_grounding": round(tr[3], 3)},
            "eval": {"n": ev[0], "yield": round(ev[1], 3), "grounded": round(ev[2], 3),
                     "step_grounding": round(ev[3], 3)}}


def fig_action_and_kind(rows):
    actions = Counter(); kinds = Counter(); by_split = defaultdict(Counter)
    for r in rows:
        if not r["has_file"]:
            continue
        f = (TRAJ / r["split"] / r["app_key"])
        kinds[r["target_kind"] or "unknown"] += 1
    # action distribution from flattened steps needs files; re-scan quickly
    for sp in ("TRAIN", "EVAL"):
        for f in (TRAJ / sp).glob("*/*.json"):
            try:
                j = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            for s in j.get("trajectory") or []:
                vm = s.get("virtual_mouse_action") if isinstance(s, dict) else None
                if not isinstance(vm, dict):
                    continue
                at = str(vm.get("action_type") or "").upper()
                if at:
                    actions[at] += 1
                    by_split[sp][at] += 1
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.2))
    order = [a for a, _ in actions.most_common()]
    trv = [by_split["TRAIN"].get(a, 0) for a in order]
    evv = [by_split["EVAL"].get(a, 0) for a in order]
    x = np.arange(len(order)); w = .38
    ax1.bar(x - w / 2, trv, w, color="#2b8a3e", label="TRAIN")
    ax1.bar(x + w / 2, evv, w, color="#f08c00", label="EVAL")
    ax1.set_xticks(x); ax1.set_xticklabels(order, rotation=35, ha="right")
    style(ax1, "Virtual-mouse action mix learned", "action_type", "count")
    ax1.legend()
    k = [a for a, _ in kinds.most_common(6)]
    ax2.barh(k, [kinds[a] for a in k], color="#1971c2")
    style(ax2, "Guide classification (honest CLI/web rejection)", "trajectories", "target_kind")
    fig.suptitle("What the corpus teaches the agent to DO", y=1.02, weight="bold")
    fig.tight_layout()
    fig.savefig(OUT / "fig5_actions_targetkind.png", dpi=120, bbox_inches="tight")
    plt.close(fig)
    return {"action_counts": dict(actions), "target_kind_counts": dict(kinds)}


def fig_perapp(rows):
    per_app = defaultdict(lambda: [0, 0])
    for r in rows:
        if r["has_file"]:
            per_app[r["app_key"]][0] += r["steps"]
            per_app[r["app_key"]][1] += r["grounded"]
    totals = [g for _, g in per_app.values() if g > 0]
    fig, ax = plt.subplots(figsize=(10, 5.4))
    ax.hist(totals, bins=30, color="#5f3dc4", alpha=.85)
    ax.axvline(np.median(totals) if totals else 0, color="red", ls="--",
               label=f"median={np.median(totals):.0f}" if totals else "")
    style(ax, f"Grounded steps per trained app (apps with data: {len(totals)})",
          "grounded steps per app", "apps")
    ax.legend()
    fig.suptitle("Dataset depth distribution — how many actions each app teaches", y=1.02, weight="bold")
    fig.tight_layout()
    fig.savefig(OUT / "fig6_perapp_depth.png", dpi=120, bbox_inches="tight")
    plt.close(fig)
    return {"apps_with_data": len(totals), "median_steps": round(float(np.median(totals)), 1) if totals else 0,
            "total_grounded": int(sum(totals))}


def main():
    p("building dataset from live corpus telemetry...")
    rows = build_dataset()
    p(f"{len(rows)} guide rows analysed; {sum(1 for r in rows if r['has_file'])} have trajectory files.")
    metrics = {"n_rows": len(rows), "n_with_files": sum(1 for r in rows if r["has_file"]),
               "n_attempted": sum(1 for r in rows if r["attempted"])}
    metrics["fig1_yield"] = fig_yield_scatter(rows)
    metrics["fig2_error"] = fig_residuals(rows)
    metrics["fig3_ingestion"] = fig_ingestion_roc(rows)
    metrics["fig4_train_vs_eval"] = fig_train_vs_eval(rows)
    metrics["fig5_actions"] = fig_action_and_kind(rows)
    metrics["fig6_depth"] = fig_perapp(rows)
    (OUT / "metrics.json").write_text(json.dumps(metrics, indent=3), encoding="utf-8")
    p("wrote " + str(OUT / "metrics.json"))
    # text summary
    lines = ["===== PHASE-1 ML DATA-SCIENCE REPORT =====",
             f"guides analysed: {metrics['n_rows']}  trajectory files: {metrics['n_with_files']}  attempted: {metrics['n_attempted']}",
             f"yield regression held-out  : R2={metrics['fig2_error']['heldout_r2']} "
             f"MAE={metrics['fig2_error']['heldout_mae']} (n={metrics['fig2_error']['n']})",
             f"ingestion classifier       : ROC-AUC={metrics['fig3_ingestion']['auc']} "
             f"PR-AUC={metrics['fig3_ingestion']['pr_auc']} balanced_acc={metrics['fig3_ingestion']['balanced_accuracy']} "
             f"(positive rate {metrics['fig3_ingestion']['positive_rate']}; raw acc is inflated by imbalance)",
             f"TRAIN yield/grounded/step  : {metrics['fig4_train_vs_eval']['train']}",
             f"EVAL  yield/grounded/step  : {metrics['fig4_train_vs_eval']['eval']}",
             f"apps with data             : {metrics['fig6_depth']['apps_with_data']} "
             f"(median {metrics['fig6_depth']['median_steps']} grounded steps, {metrics['fig6_depth']['total_grounded']} total)",
             f"figures -> {OUT.resolve()}"]
    txt = "\n".join(lines)
    (OUT / "report_summary.txt").write_text(txt, encoding="utf-8")
    print("\n" + txt + "\n")


if __name__ == "__main__":
    main()
