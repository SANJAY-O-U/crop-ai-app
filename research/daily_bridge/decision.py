"""Pre-declared evidence rule (config.EVIDENCE_RULE). Rainfall defaults to pass-through."""

from daily_bridge import config
from daily_bridge.metrics import skill_label


def decide(daily_var: str, evidence: dict) -> dict:
    """evidence: {pooled_mae_skill, pooled_rmse_skill, folds_mae_positive, quarters_mae_positive,
    ci_lower_mae_skill, mae_skill_vs_production}. Every criterion must hold; otherwise PASS_THROUGH."""
    r = config.EVIDENCE_RULE
    checks = {
        "pooled_mae_skill_vs_block": (evidence.get("pooled_mae_skill") or -1) > r["pooled_mae_skill_vs_block_gt"],
        "pooled_rmse_skill_vs_block": (evidence.get("pooled_rmse_skill") or -1) > r["pooled_rmse_skill_vs_block_gt"],
        "folds_mae_positive": evidence.get("folds_mae_positive", 0) >= r["min_folds_mae_positive_of_4"],
        "quarters_mae_positive": evidence.get("quarters_mae_positive", 0) >= r["min_quarters_mae_positive_of_4"],
        "bootstrap_ci_lower_above_zero": (evidence.get("ci_lower_mae_skill") if evidence.get("ci_lower_mae_skill") is not None else -1) > r["bootstrap_ci_lower_mae_skill_gt"],
        "beats_production_baseline_mae": (evidence.get("mae_skill_vs_production") or -1) > 0,
    }
    passed = all(checks.values())
    return {"variable": daily_var, "decision": "CANDIDATE_MEETS_PROPOSED_EVIDENCE_RULE" if passed else "KEEP_PASS_THROUGH",
            "criteria": checks, "rainfall_default_pass_through": daily_var == "rainfall_mm" and not passed,
            "note": "Meeting the rule is necessary, not sufficient, to deploy: see report limitations (input mismatch, no forecast-input validation)."}
