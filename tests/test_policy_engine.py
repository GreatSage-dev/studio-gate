"""Unit tests for the deterministic policy engine.

These tests verify that the verdict logic is pure arithmetic
with no external dependencies.
"""
import pytest
from studiogate.policy_engine import evaluate_policy, compute_job_cost


class TestComputeJobCost:
    def test_basic_cost(self):
        assert compute_job_cost(100.0, 0.01) == 1.0

    def test_zero_duration(self):
        assert compute_job_cost(0.0, 0.01) == 0.0

    def test_zero_rate(self):
        assert compute_job_cost(100.0, 0.0) == 0.0

    def test_rounding(self):
        # 3600 * 0.0045 = 16.2 exactly
        assert compute_job_cost(3600.0, 0.0045) == 16.2

    def test_high_cost_render(self):
        # 8K render: 1800s at $0.015/s = $27.00
        assert compute_job_cost(1800.0, 0.015) == 27.0


class TestEvaluatePolicy:
    def test_approved_under_budget(self):
        result = evaluate_policy(
            rolling_burn_usd=200.0,
            requested_job_cost_usd=50.0,
            hard_budget_cap_usd=500.0,
        )
        assert result["verdict"] == "APPROVED"
        assert result["projected_total"] == 250.0
        assert result["overage"] == 0.0

    def test_blocked_over_budget(self):
        result = evaluate_policy(
            rolling_burn_usd=480.0,
            requested_job_cost_usd=50.0,
            hard_budget_cap_usd=500.0,
        )
        assert result["verdict"] == "BLOCKED"
        assert result["projected_total"] == 530.0
        assert result["overage"] == 30.0

    def test_exact_boundary_approved(self):
        """When projected == cap, it should be APPROVED (not strictly greater)."""
        result = evaluate_policy(
            rolling_burn_usd=450.0,
            requested_job_cost_usd=50.0,
            hard_budget_cap_usd=500.0,
        )
        assert result["verdict"] == "APPROVED"
        assert result["projected_total"] == 500.0
        assert result["overage"] == 0.0

    def test_just_over_boundary_blocked(self):
        result = evaluate_policy(
            rolling_burn_usd=450.0,
            requested_job_cost_usd=50.01,
            hard_budget_cap_usd=500.0,
        )
        assert result["verdict"] == "BLOCKED"
        assert result["overage"] == 0.01

    def test_zero_burn_approved(self):
        result = evaluate_policy(
            rolling_burn_usd=0.0,
            requested_job_cost_usd=100.0,
            hard_budget_cap_usd=500.0,
        )
        assert result["verdict"] == "APPROVED"

    def test_massive_overage(self):
        result = evaluate_policy(
            rolling_burn_usd=400.0,
            requested_job_cost_usd=4200.0,
            hard_budget_cap_usd=500.0,
        )
        assert result["verdict"] == "BLOCKED"
        assert result["overage"] == 4100.0

    def test_result_contains_all_inputs(self):
        """Every decision must carry its inputs for auditability."""
        result = evaluate_policy(
            rolling_burn_usd=100.0,
            requested_job_cost_usd=50.0,
            hard_budget_cap_usd=500.0,
        )
        assert result["rolling_burn_usd"] == 100.0
        assert result["requested_job_cost_usd"] == 50.0
        assert result["hard_budget_cap_usd"] == 500.0
