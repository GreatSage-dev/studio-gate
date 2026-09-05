"""Cryptographic SHA-256 hash-chaining core implementation."""

from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Dict, List, Optional, Tuple, Union

GENESIS_HASH: str = "0" * 64


def format_timestamp(ts: Union[str, datetime, Any]) -> str:
    """Ensure consistent ISO string representation of timestamp for deterministic hashing."""
    if isinstance(ts, datetime):
        return ts.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    return str(ts)


def build_canonical_payload(data: Union[Dict[str, Any], str, Any]) -> str:
    """Generate a strictly deterministic, canonical JSON representation.
    
    Keys are sorted and compact separators are used to eliminate whitespace ambiguity.
    """
    if isinstance(data, dict):
        return json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)
    elif isinstance(data, str):
        return data
    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)


def compute_entry_hash(
    timestamp: Union[str, datetime],
    payload: Union[Dict[str, Any], str],
    prev_hash: str,
) -> str:
    """Compute SHA-256 hash over timestamp, canonical payload, and previous hash."""
    ts_str = format_timestamp(timestamp)
    payload_str = build_canonical_payload(payload) if not isinstance(payload, str) else payload
    combined = f"{ts_str}{payload_str}{prev_hash}"
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


def verify_chain(
    chain: List[Dict[str, Any]],
    payload_key: str = "payload",
    timestamp_key: str = "timestamp",
    prev_hash_key: str = "prev_hash",
    entry_hash_key: str = "entry_hash",
) -> Tuple[bool, Optional[str]]:
    """Walk an entire hash-chain and verify cryptographic continuity and integrity.
    
    Returns (True, None) if the chain is valid.
    Returns (False, error_message) if any link or hash is broken.
    """
    if not chain:
        return True, None

    expected_prev = GENESIS_HASH

    for i, row in enumerate(chain):
        ts = row.get(timestamp_key)
        payload = row.get(payload_key)
        
        # If payload_key is not in dict, use the row itself excluding hash keys
        if payload is None:
            payload = {
                k: v for k, v in row.items() 
                if k not in (prev_hash_key, entry_hash_key, "decision_id", "id")
            }

        prev_hash = row.get(prev_hash_key)
        entry_hash = row.get(entry_hash_key)

        if isinstance(prev_hash, bytes):
            prev_hash = prev_hash.decode("utf-8")
        else:
            prev_hash = str(prev_hash or "")

        if isinstance(entry_hash, bytes):
            entry_hash = entry_hash.decode("utf-8")
        else:
            entry_hash = str(entry_hash or "")

        # 1. Verify link to previous entry
        if prev_hash != expected_prev:
            return False, (
                f"Linkage break at block index {i}: "
                f"stored prev_hash '{prev_hash}' does not match expected '{expected_prev}'"
            )

        # 2. Verify hash calculation of current entry
        canonical_str = build_canonical_payload(payload)
        computed_hash = compute_entry_hash(ts, canonical_str, prev_hash)

        if entry_hash != computed_hash:
            return False, (
                f"Tamper detected at block index {i}: "
                f"stored entry_hash '{entry_hash}' does not match computed '{computed_hash}'"
            )

        expected_prev = entry_hash

    return True, None


class HashLedger:
    """In-memory append-only cryptographically chained ledger."""

    def __init__(self) -> None:
        self.entries: List[Dict[str, Any]] = []

    @property
    def latest_hash(self) -> str:
        return self.entries[-1]["entry_hash"] if self.entries else GENESIS_HASH

    def append(
        self,
        payload: Union[Dict[str, Any], str],
        timestamp: Optional[Union[str, datetime]] = None,
    ) -> Dict[str, Any]:
        """Append a new payload to the hash-chain."""
        if timestamp is None:
            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        
        prev = self.latest_hash
        canonical_str = build_canonical_payload(payload)
        entry_hash = compute_entry_hash(timestamp, canonical_str, prev)

        entry = {
            "index": len(self.entries),
            "timestamp": format_timestamp(timestamp),
            "payload": payload,
            "canonical_payload": canonical_str,
            "prev_hash": prev,
            "entry_hash": entry_hash,
        }
        self.entries.append(entry)
        return entry

    def verify(self) -> Tuple[bool, Optional[str]]:
        """Verify the full integrity of all recorded entries."""
        return verify_chain(self.entries)

    def __len__(self) -> int:
        return len(self.entries)
