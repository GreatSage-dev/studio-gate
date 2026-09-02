"""Deterministic policy engine for StudioGate.

The pass/fail decision is a plain code comparison, never an LLM judgment.
This is the most important architectural rule of the entire system.
"""


def compute_job_cost(duration_sec: float, gpu_cost_per_sec: float) -> float:
    """Calculate the total cost of a render job.
    
    Args:
        duration_sec: Estimated job duration in seconds.
        gpu_cost_per_sec: GPU cost rate in USD per second.
    
    Returns:
        Total estimated job cost in USD, rounded to 2 decimal places.
    """
    return round(duration_sec * gpu_cost_per_sec, 2)


def evaluate_policy(
    rolling_burn_usd: float,
    requested_job_cost_usd: float,
    hard_budget_cap_usd: float,
) -> dict:
    """Evaluate a render job request against the budget policy.
    
    This function makes the APPROVED/BLOCKED decision using pure arithmetic.
    No LLM is involved. The projected total (current burn + requested cost)
    is compared against the hard budget cap.
    
    Args:
        rolling_burn_usd: Current 1-hour rolling burn from ClickHouse.
        requested_job_cost_usd: Cost of the requested render job.
        hard_budget_cap_usd: Hard budget ceiling in USD.
    
    Returns:
        Dict with verdict ('APPROVED' or 'BLOCKED'), projected_total,
        overage amount, and all input values for auditability.
    """
    projected_total = round(rolling_burn_usd + requested_job_cost_usd, 2)
    
    if projected_total > hard_budget_cap_usd:
        return {
            "verdict": "BLOCKED",
            "projected_total": projected_total,
            "overage": round(projected_total - hard_budget_cap_usd, 2),
            "rolling_burn_usd": rolling_burn_usd,
            "requested_job_cost_usd": requested_job_cost_usd,
            "hard_budget_cap_usd": hard_budget_cap_usd,
        }
    
    return {
        "verdict": "APPROVED",
        "projected_total": projected_total,
        "overage": 0.0,
        "rolling_burn_usd": rolling_burn_usd,
        "requested_job_cost_usd": requested_job_cost_usd,
        "hard_budget_cap_usd": hard_budget_cap_usd,
    }
