"""Unit tests for the cryptographic hash-chain logic.

These tests verify tamper detection, genesis handling,
and chain verification without any external dependencies.
"""
import copy
import pytest
from studiogate.hash_chain import (
    GENESIS_HASH,
    compute_entry_hash,
    build_decision_payload,
    verify_chain,
)


class TestComputeEntryHash:
    def test_deterministic(self):
        """Same inputs must always produce the same hash."""
        h1 = compute_entry_hash("2026-01-01T00:00:00.000", '{"verdict":"APPROVED"}', GENESIS_HASH)
        h2 = compute_entry_hash("2026-01-01T00:00:00.000", '{"verdict":"APPROVED"}', GENESIS_HASH)
        assert h1 == h2

    def test_returns_64_hex_chars(self):
        h = compute_entry_hash("2026-01-01T00:00:00.000", '{"verdict":"APPROVED"}', GENESIS_HASH)
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_different_timestamp_different_hash(self):
        h1 = compute_entry_hash("2026-01-01T00:00:00.000", '{"verdict":"APPROVED"}', GENESIS_HASH)
        h2 = compute_entry_hash("2026-01-01T00:00:01.000", '{"verdict":"APPROVED"}', GENESIS_HASH)
        assert h1 != h2

    def test_different_payload_different_hash(self):
        h1 = compute_entry_hash("2026-01-01T00:00:00.000", '{"verdict":"APPROVED"}', GENESIS_HASH)
        h2 = compute_entry_hash("2026-01-01T00:00:00.000", '{"verdict":"BLOCKED"}', GENESIS_HASH)
        assert h1 != h2

    def test_different_prev_hash_different_hash(self):
        h1 = compute_entry_hash("2026-01-01T00:00:00.000", '{"verdict":"APPROVED"}', GENESIS_HASH)
        h2 = compute_entry_hash("2026-01-01T00:00:00.000", '{"verdict":"APPROVED"}', "a" * 64)
        assert h1 != h2

    def test_genesis_hash_is_64_zeros(self):
        assert GENESIS_HASH == "0" * 64
        assert len(GENESIS_HASH) == 64


class TestBuildDecisionPayload:
    def test_sorted_keys(self):
        """Keys must be sorted for deterministic hashing."""
        payload = build_decision_payload({"target_job": "render", "verdict": "APPROVED"})
        assert '"policy_threshold_usd":0.0' in payload
        assert '"target_job":"render"' in payload

    def test_compact_separators(self):
        """No unnecessary whitespace in the JSON output."""
        payload = build_decision_payload({"target_job": "8k_render", "verdict": "APPROVED"})
        assert ": " not in payload

    def test_same_data_same_output(self):
        d1 = {"verdict": "BLOCKED", "rolling_burn_usd": 30.0, "target_job": "test"}
        d2 = {"rolling_burn_usd": 30.0, "verdict": "BLOCKED", "target_job": "test"}
        assert build_decision_payload(d1) == build_decision_payload(d2)


def _make_chain(n: int) -> list[dict]:
    """Helper: build a valid chain of n ledger rows."""
    rows = []
    prev_hash = GENESIS_HASH
    for i in range(n):
        ts = f"2026-01-01 00:00:{i:02d}.000"
        row_data = {
            "decision_id": f"id-{i}",
            "timestamp": ts,
            "target_job": f"job-{i}",
            "rolling_burn_usd": 100.0 + i,
            "policy_threshold_usd": 500.0,
            "verdict": "APPROVED",
            "remedy_suggestion": "",
            "prev_hash": prev_hash,
        }
        payload = build_decision_payload(row_data)
        entry_hash = compute_entry_hash(ts, payload, prev_hash)
        row_data["entry_hash"] = entry_hash
        rows.append(row_data)
        prev_hash = entry_hash
    return rows


class TestVerifyChain:
    def test_empty_chain_valid(self):
        is_valid, error = verify_chain([])
        assert is_valid is True
        assert error is None

    def test_single_entry_valid(self):
        chain = _make_chain(1)
        is_valid, error = verify_chain(chain)
        assert is_valid is True
        assert error is None

    def test_five_entry_chain_valid(self):
        chain = _make_chain(5)
        is_valid, error = verify_chain(chain)
        assert is_valid is True
        assert error is None

    def test_tampered_entry_hash_detected(self):
        """Changing an entry_hash must break the chain."""
        chain = _make_chain(5)
        chain[2]["entry_hash"] = "f" * 64  # tamper
        is_valid, error = verify_chain(chain)
        assert is_valid is False
        assert "row 2" in error

    def test_tampered_prev_hash_detected(self):
        """Changing a prev_hash must break the chain."""
        chain = _make_chain(5)
        chain[3]["prev_hash"] = "a" * 64  # tamper
        is_valid, error = verify_chain(chain)
        assert is_valid is False
        assert "row 3" in error

    def test_tampered_data_detected(self):
        """Changing a data field must invalidate the entry hash."""
        chain = _make_chain(5)
        chain[1]["verdict"] = "BLOCKED"  # tamper the data
        is_valid, error = verify_chain(chain)
        assert is_valid is False
        assert "row 1" in error
