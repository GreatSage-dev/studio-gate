"""Integration tests for the ClickHouse client layer.

These tests require a running ClickHouse instance with seeded data.
Run `python seed_telemetry.py` before running these tests.

Skip these tests in CI by setting SKIP_INTEGRATION_TESTS=1.
"""
import os
import pytest

# Skip all tests in this module if no ClickHouse connection is available
pytestmark = pytest.mark.skipif(
    os.getenv("SKIP_INTEGRATION_TESTS", "0") == "1",
    reason="Integration tests skipped (SKIP_INTEGRATION_TESTS=1)",
)


@pytest.fixture(scope="module")
def ch_client():
    """Create a shared ClickHouse client for all tests in this module."""
    from studiogate.clickhouse_client import get_client, create_governance_ledger_table

    client = get_client()
    create_governance_ledger_table(client)
    return client


class TestGetRollingBurn:
    def test_returns_dict_with_expected_keys(self, ch_client):
        from studiogate.clickhouse_client import get_rolling_burn

        result = get_rolling_burn(ch_client)
        assert "rolling_burn_usd" in result
        assert "avg_power_kw" in result
        assert "total_samples" in result

    def test_returns_nonzero_data(self, ch_client):
        """Requires seed_telemetry.py to have been run recently."""
        from studiogate.clickhouse_client import get_rolling_burn

        result = get_rolling_burn(ch_client)
        assert result["total_samples"] > 0, (
            "0 samples in the last hour. Run seed_telemetry.py first."
        )
        assert result["rolling_burn_usd"] > 0

    def test_burn_is_float(self, ch_client):
        from studiogate.clickhouse_client import get_rolling_burn

        result = get_rolling_burn(ch_client)
        assert isinstance(result["rolling_burn_usd"], float)
        assert isinstance(result["avg_power_kw"], float)


class TestLedgerOperations:
    def test_write_and_read_entry(self, ch_client):
        """Write a ledger entry and verify it appears in the full ledger."""
        from studiogate.clickhouse_client import write_ledger_entry, read_full_ledger

        policy_result = {
            "verdict": "APPROVED",
            "projected_total": 250.0,
            "overage": 0.0,
            "rolling_burn_usd": 200.0,
            "requested_job_cost_usd": 50.0,
            "hard_budget_cap_usd": 500.0,
        }

        entry = write_ledger_entry(
            target_job="test_8k_render",
            rolling_burn_usd=200.0,
            policy_threshold_usd=500.0,
            verdict="APPROVED",
            policy_result=policy_result,
            client=ch_client,
        )

        assert entry["decision_id"]
        assert entry["entry_hash"]
        assert len(entry["entry_hash"]) == 64
        assert entry["verdict"] == "APPROVED"

    def test_hash_chain_linkage(self, ch_client):
        """Write two entries and verify the second links to the first."""
        from studiogate.clickhouse_client import write_ledger_entry, get_latest_entry_hash
        import time

        policy_result_1 = {
            "verdict": "APPROVED",
            "projected_total": 100.0,
            "overage": 0.0,
            "rolling_burn_usd": 50.0,
            "requested_job_cost_usd": 50.0,
            "hard_budget_cap_usd": 500.0,
        }

        entry_1 = write_ledger_entry(
            target_job="chain_test_job_1",
            rolling_burn_usd=50.0,
            policy_threshold_usd=500.0,
            verdict="APPROVED",
            policy_result=policy_result_1,
            client=ch_client,
        )

        # Small delay to ensure ClickHouse processes the insert
        time.sleep(1)

        policy_result_2 = {
            "verdict": "BLOCKED",
            "projected_total": 600.0,
            "overage": 100.0,
            "rolling_burn_usd": 400.0,
            "requested_job_cost_usd": 200.0,
            "hard_budget_cap_usd": 500.0,
        }

        entry_2 = write_ledger_entry(
            target_job="chain_test_job_2",
            rolling_burn_usd=400.0,
            policy_threshold_usd=500.0,
            verdict="BLOCKED",
            policy_result=policy_result_2,
            client=ch_client,
        )

        # Entry 2's prev_hash should be entry 1's entry_hash
        assert entry_2["prev_hash"] == entry_1["entry_hash"]
