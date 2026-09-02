"""Cryptographic hash-chain logic for the StudioGate governance ledger.

Every governance decision (approved or blocked) is written to a
hash-chained audit ledger. Each entry's hash is computed from its
own data plus the previous entry's hash, creating a tamper-evident
log that can be verified by walking the entire chain.
"""
from datetime import datetime
import hashlib
import json
from typing import Optional, Union


# The genesis hash used as prev_hash for the very first ledger entry.
GENESIS_HASH = "0" * 64


def format_timestamp_str(ts: Union[str, datetime]) -> str:
    """Ensure consistent ISO string representation of timestamp for hashing."""
    if isinstance(ts, datetime):
        return ts.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    return str(ts)


def compute_entry_hash(timestamp: Union[str, datetime], decision_payload: str, prev_hash: str) -> str:
    """Compute the SHA-256 hash for a single ledger entry.
    
    The hash is derived from the concatenation of:
    - The entry's timestamp (formatted string)
    - The decision payload (canonical deterministic string)
    - The previous entry's hash
    
    Args:
        timestamp: ISO-format timestamp string or datetime.
        decision_payload: Deterministic string of the decision data.
        prev_hash: The entry_hash of the previous ledger row,
                   or GENESIS_HASH if this is the first entry.
    
    Returns:
        64-character hex SHA-256 digest.
    """
    ts_str = format_timestamp_str(timestamp)
    combined = f"{ts_str}{decision_payload}{prev_hash}"
    return hashlib.sha256(combined.encode()).hexdigest()


def build_decision_payload(decision: dict) -> str:
    """Create a deterministic canonical string from ledger row attributes.
    
    Uses canonical JSON with sorted keys to ensure exact reproducibility
    across write and read/verification cycles.
    """
    payload_data = {
        "policy_threshold_usd": round(float(decision.get("policy_threshold_usd", decision.get("hard_budget_cap_usd", 0.0))), 2),
        "remedy_suggestion": str(decision.get("remedy_suggestion", "")),
        "rolling_burn_usd": round(float(decision.get("rolling_burn_usd", 0.0)), 2),
        "target_job": str(decision.get("target_job", "")),
        "verdict": str(decision.get("verdict", "")),
    }
    return json.dumps(payload_data, sort_keys=True, separators=(",", ":"))


def verify_chain(ledger_rows: list[dict]) -> tuple[bool, Optional[str]]:
    """Walk the entire governance ledger and verify hash-chain integrity.
    
    Each row's entry_hash must equal the SHA-256 of:
        timestamp + decision_payload + previous_row's_entry_hash
    
    The first row uses GENESIS_HASH as its prev_hash.
    
    Args:
        ledger_rows: List of ledger row dicts, ordered by timestamp ASC.
    
    Returns:
        Tuple of (is_valid: bool, error_message: Optional[str]).
        If valid, error_message is None.
    """
    if not ledger_rows:
        return True, None
    
    prev_hash = GENESIS_HASH
    
    for i, row in enumerate(ledger_rows):
        decision_payload = build_decision_payload(row)
        
        expected_hash = compute_entry_hash(
            row["timestamp"],
            decision_payload,
            prev_hash,
        )
        
        # Verify prev_hash linkage
        row_prev = row["prev_hash"].decode("utf-8") if isinstance(row["prev_hash"], bytes) else str(row["prev_hash"])
        row_entry = row["entry_hash"].decode("utf-8") if isinstance(row["entry_hash"], bytes) else str(row["entry_hash"])
        
        if row_prev != prev_hash:
            return False, (
                f"Chain broken at row {i} (decision_id={row.get('decision_id', '?')}): "
                f"stored prev_hash={row_prev} but expected {prev_hash}"
            )
        
        # Verify entry_hash correctness
        if row_entry != expected_hash:
            return False, (
                f"Hash mismatch at row {i} (decision_id={row.get('decision_id', '?')}): "
                f"stored entry_hash={row_entry} but computed {expected_hash}"
            )
        
        prev_hash = row_entry
    
    return True, None
