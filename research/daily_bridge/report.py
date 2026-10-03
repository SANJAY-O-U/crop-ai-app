"""Human-readable report generated from the results dict. Wording follows the numbers; nothing is hand-edited."""

from daily_bridge import config
from daily_bridge.metrics import skill_label

DEPLOYABLE_GRAIN = ["C_daily_hgb", "R_daily_ridge"]          # use only inputs the daily API can provide
NAMES = {"temperature_max_c": "Temperature (daily max)", "temperature_min_c": "Temperature (daily min)",
         "humidity_pct": "Humidity (daily mean)", "wind_kmph": "Wind (daily max)", "rainfall_mm": "Rainfall (daily total)"}


ORDER = [config.BLOCK, config.PRODUCTION, config.OFFSET] + config.CANDIDATES


def _f(v, d=3):
    return "n/a" if v is None else f"{v:.{d}f}"


def _pct(v):
    return "n/a" if v is None else f"{v * 100:+.1f}%"


def _sk(e, m):
    s = e["skill"][m]
    b = s["bootstrap_vs_block"]["mae"]["ci95"]
    return (f"{m}: MAE skill {_pct(s['vs_block']['mae'])} ({s['labels_vs_block']['mae']}; 95% CI {b[0] * 100:+.1f}% to {b[1] * 100:+.1f}%), "
            f"RMSE skill {_pct(s['vs_block']['rmse'])} ({s['labels_vs_block']['rmse']}), "
            f"folds with MAE gain {s['folds_mae_positive_of_4']}/4, quarters {s['quarters_mae_positive_of_4']}/4")


def _obs_flag(obs, dv):
    """None if no observation check exists for this variable; True if it contradicts the hourly correction."""
    if not obs or "by_variable" not in obs or dv not in obs["by_variable"] or dv == "rainfall_mm":
        return None
    e = obs["by_variable"][dv]
    ci = e["bootstrap_C4_vs_A1"]["mae"]["ci95"]
    return {"label": e["skill_C4_vs_A1_label_mae"], "mae_skill": e["skill_C4_vs_A1"]["mae"], "ci": ci,
            "contradicts": e["skill_C4_vs_A1"]["mae"] is not None and ci[1] < 0}


def render(r: dict) -> str:
    R, D, obs = r["results_by_variable"], r["decisions"], r.get("observation_diagnostic")
    L = []
    w = L.append
    w("# CropCastAI - offline daily evaluation bridge\n")
    w(f"**{r['framing']}** The station diagnostic (section 8) is separate and is never pooled with it. Nothing here is deployed; "
      "no model is saved; the live API and the frontend are unchanged.\n")
    w(f"Run: {r['created_utc']} - commit `{r['provenance']['git_commit'][:10]}` - dataset `{r['provenance']['dataset']}` "
      f"(sha256 `{r['provenance']['dataset_sha256'][:16]}...`, {r['provenance']['dataset_rows']:,} hourly rows) - runtime {r['runtime_s']} s.\n")

    # ---- decisions ------------------------------------------------------------------------
    proceed, hold = [], []
    for dv in config.DAILY_VARIABLES:
        meets = [m for m in DEPLOYABLE_GRAIN if D[dv][m]["decision"] == "CANDIDATE_MEETS_PROPOSED_EVIDENCE_RULE"]
        flag = _obs_flag(obs, dv)
        if meets and not (flag and flag["contradicts"]):
            proceed.append((dv, meets, flag))
        else:
            hold.append(dv)
    w("## Bottom line\n")
    if proceed:
        w("Variables whose daily-grain candidates meet the pre-declared evidence rule against the ERA5-Land proxy "
          "(necessary, not sufficient, to build a deployable model):\n")
        for dv, meets, flag in proceed:
            off = R[dv]["skill"][meets[0]]["mae_skill_vs_constant_offset_diagnostic"]
            obs_txt = "no station check available" if flag is None else f"station diagnostic of the hourly correction: {flag['label']} (MAE skill {_pct(flag['mae_skill'])})"
            note = f"MAE skill vs the constant-offset diagnostic {_pct(off)}; {obs_txt}"
            w(f"- **{NAMES[dv]}**: {', '.join(meets)} - {note}")
        w("")
    w("Variables that should **stay pass-through (block value / current behaviour) for now**: " +
      (", ".join(NAMES[v] for v in hold) if hold else "none") + ".\n")
    w("No statement here is a claim of accuracy: all numbers measure agreement with ERA5-Land from ERA5 reanalysis inputs, "
      "not with real Panchayat weather and not with an NWP forecast.\n")

    # ---- answers --------------------------------------------------------------------------
    w("## Answers\n")
    def block(title, dvs, cands):
        w(f"**{title}**\n")
        for dv in dvs:
            w(f"- {NAMES[dv]}:")
            for m in cands:
                w(f"  - {_sk(R[dv], m)}")
        w("")
    block("1. Does daily correction improve temperature?", ["temperature_max_c", "temperature_min_c"], DEPLOYABLE_GRAIN + ["C_hourly_agg"])
    block("2. Humidity?", ["humidity_pct"], DEPLOYABLE_GRAIN + ["C_hourly_agg"])
    block("3. Wind?", ["wind_kmph"], DEPLOYABLE_GRAIN + ["C_hourly_agg"])
    block("4. Rainfall?", ["rainfall_mm"], DEPLOYABLE_GRAIN + ["C_hourly_agg"])
    w("**5. Does it outperform block-as-is?** See the skill lines above: a candidate outperforms block-as-is only where its MAE and RMSE "
      "skill are both labelled positive with a bootstrap interval above zero.\n")
    w("**6. Does it outperform the current production baseline?**\n")
    for dv in config.DAILY_VARIABLES:
        p = R[dv]["skill"][config.PRODUCTION]
        parts = [f"production baseline vs block: MAE skill {_pct(p['vs_block']['mae'])} ({p['labels_vs_block']['mae']})"]
        parts.append(f"constant-offset diagnostic vs block: MAE skill {_pct(R[dv]['skill'][config.OFFSET]['vs_block']['mae'])}")
        for m in config.CANDIDATES:
            parts.append(f"{m} vs production: MAE skill {_pct(R[dv]['skill'][m]['mae_skill_vs_production_baseline'])}")
        w(f"- {NAMES[dv]}: " + "; ".join(parts))
    w("")
    w("**7. Stability across spatial and temporal splits** - folds = the 4 held-out cell groups; quarters = Q1-Q4 of the 2023 test year. "
      "Counts of folds/quarters with a MAE gain are in the skill lines and tables below.\n")
    w("**8. Real observations** - see section 8.\n")
    w("**9/10. Which variables proceed / stay pass-through** - see Bottom line. Rule (pre-declared in `config.py`): " +
      "; ".join(f"{k} = {v}" for k, v in r["evidence_rule"].items()) + ".\n")

    # ---- tables ---------------------------------------------------------------------------
    w("## 1. Pooled results by variable (10 GPs, 2023 test days)\n")
    for dv in config.DAILY_VARIABLES:
        e = R[dv]
        w(f"### {NAMES[dv]} ({e['unit']}) - n = {e['n_pooled']:,} GP-days\n")
        w("| method | MAE | RMSE | bias | MAE skill vs block | RMSE skill vs block | folds MAE gain | quarters MAE gain |")
        w("|---|---|---|---|---|---|---|---|")
        for m in ORDER:
            x = e["methods"][m]
            if m == config.BLOCK:
                w(f"| {m} | {_f(x['mae'])} | {_f(x['rmse'])} | {_f(x['bias'])} | reference | reference | - | - |")
            else:
                s = e["skill"][m]
                w(f"| {m} | {_f(x['mae'])} | {_f(x['rmse'])} | {_f(x['bias'])} | {_pct(s['vs_block']['mae'])} ({s['labels_vs_block']['mae']}) | "
                  f"{_pct(s['vs_block']['rmse'])} ({s['labels_vs_block']['rmse']}) | {s['folds_mae_positive_of_4']}/4 | {s['quarters_mae_positive_of_4']}/4 |")
        w("")
        w("Per fold MAE (held-out cell group) - " + "; ".join(
            f"{f.split('_')[-1]}: " + ", ".join(f"{m}={_f(v['methods'][m]['mae'])}" for m in [config.BLOCK, config.PRODUCTION, 'C_daily_hgb'])
            for f, v in e["by_fold"].items()) + "\n")
        w("Per quarter MAE - " + "; ".join(
            f"{q}: " + ", ".join(f"{m}={_f(v['methods'][m]['mae'])}" for m in [config.BLOCK, config.PRODUCTION, 'C_daily_hgb'])
            for q, v in e["by_quarter"].items()) + "\n")
        w("Decision per candidate: " + "; ".join(f"{m}: {D[dv][m]['decision']}" for m in config.CANDIDATES) + "\n")

    w("## 2. Hourly -> daily aggregation (input -> aggregation -> output -> units)\n")
    w("| hourly input | aggregation | daily output | unit | mirrors Open-Meteo field |\n|---|---|---|---|---|")
    for a in r["aggregation"]:
        w(f"| {a['input_hourly']} | {a['aggregation']} | {a['output_daily']} | {a['unit']} | {a['mirrors_open_meteo_field']} |")
    w(f"\n{r['day_definition']}\n")
    w("## 3. Baselines and candidates\n")
    for k, v in r["methods"].items():
        w(f"- **{k}**: {v}")
    w(f"\nBlock input: {r['block_input_definition']}\n")
    w(f"Daily features: {', '.join(r['features_daily'])}. HGB config: `{r['model_config_hgb']}`; ridge alpha {r['ridge_alpha']}.\n")
    w("## 4. Splits\n")
    for k, v in r["split"].items():
        if k != "audits":
            w(f"- **{k}**: {v}")
    w("\nPer fold audit:\n")
    for f, a in r["split"]["audits"].items():
        w(f"- {f}: held-out `{a['held_out_cell_group']}`; train days {a['train_days'][0]}..{a['train_days'][1]}; test days {a['test_days'][0]}..{a['test_days'][1]}; "
          f"gap {a['gap_days_between_last_train_and_first_test_day']} d; train GP-days {a['n_train_gp_days']:,}; test GP-days {a['n_test_gp_days']:,}; cell groups disjoint: {a['cell_groups_disjoint']}")
    w(f"\nSkill: {r['skill_definition']}\n")

    w("## 8. Station-observation diagnostic (independent of the ERA5-Land proxy)\n")
    if not obs or "unavailable" in (obs or {}):
        w(f"Not available in this run: {(obs or {}).get('unavailable', 'skipped')}\n")
    else:
        w(obs["framing"] + f" Station-days need at least {obs['min_matched_hours_per_day']} matched hours. " + obs["note_rainfall"] + "\n")
        w("| daily variable | station-days | A1 (coarse) MAE | C4 hourly-agg MAE | ERA5-Land target MAE | C4 MAE skill vs A1 | 95% CI | label |")
        w("|---|---|---|---|---|---|---|---|")
        for dv, e in obs["by_variable"].items():
            ci = e["bootstrap_C4_vs_A1"]["mae"]["ci95"]
            w(f"| {NAMES.get(dv, dv)} | {e['n_station_days']} | {_f(e['methods']['A1_bilinear']['mae'])} | {_f(e['methods']['C4']['mae'])} | "
              f"{_f(e['methods']['ERA5L_target']['mae'])} | {_pct(e['skill_C4_vs_A1']['mae'])} | {ci[0] * 100:+.1f}% to {ci[1] * 100:+.1f}% | {e['skill_C4_vs_A1_label_mae']} |")
        w("")
        w("Per station (C4 MAE skill vs A1): " + "; ".join(
            f"{NAMES.get(dv, dv)} - " + ", ".join(f"{v['region']}: {_pct(v['skill_mae_C4_vs_A1'])} (n={v['n']})" for v in e["per_station"].values())
            for dv, e in obs["by_variable"].items()) + "\n")

    w("## Limitations\n")
    for x in r["limitations"]:
        w(f"- {x}")
    return "\n".join(L) + "\n"
