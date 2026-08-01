"""VacancyGateCheck — thin pre-scoring filter: Gate A (remote/salary/location) + Gate B (archetype).

Reuses UESCalculator internally. No full scoring, no risks, no recommendation.
Useful for fast pre-filtering in mass-scan pipelines before calling UESCalculator.evaluate().
"""
from src.ues import UESCalculator, load_ues_config


def evaluate(vacancy: dict, config: dict | None = None) -> dict:
    """Returns only gate_a + gate_b pass/fail. No scoring."""
    cfg = config or load_ues_config()
    calc = UESCalculator(cfg)
    gate_a = calc._check_gate_a(vacancy)
    gate_b = calc._check_gate_b(vacancy)
    return {
        "gate_a": gate_a,
        "gate_b": gate_b,
        "passed": gate_a["passed"] and gate_b["passed"],
    }
