"""Unit tests for hashledger package."""

import pytest
from hashledger import HashLedger, GENESIS_HASH, verify_chain, compute_entry_hash

def test_genesis_link():
    ledger = HashLedger()
    entry = ledger.append({"action": "INIT"})
    assert entry["prev_hash"] == GENESIS_HASH
    assert len(entry["entry_hash"]) == 64
    assert len(ledger) == 1

def test_chain_continuity():
    ledger = HashLedger()
    e1 = ledger.append({"job": "render_01", "cost": 50.0})
    e2 = ledger.append({"job": "render_02", "cost": 120.0})
    e3 = ledger.append({"job": "render_03", "cost": 30.0})

    assert e2["prev_hash"] == e1["entry_hash"]
    assert e3["prev_hash"] == e2["entry_hash"]

    is_valid, err = ledger.verify()
    assert is_valid is True
    assert err is None

def test_tamper_detection_on_payload():
    ledger = HashLedger()
    ledger.append({"job": "render_01", "cost": 50.0})
    ledger.append({"job": "render_02", "cost": 120.0})
    
    # Tamper with block 0 payload
    ledger.entries[0]["payload"]["cost"] = 999.0
    
    is_valid, err = ledger.verify()
    assert is_valid is False
    assert "Tamper detected at block index 0" in err

def test_tamper_detection_on_hash_link():
    ledger = HashLedger()
    ledger.append({"job": "render_01", "cost": 50.0})
    ledger.append({"job": "render_02", "cost": 120.0})

    # Tamper with prev_hash link
    ledger.entries[1]["prev_hash"] = "f" * 64

    is_valid, err = ledger.verify()
    assert is_valid is False
    assert "Linkage break at block index 1" in err

def test_empty_chain_is_valid():
    is_valid, err = verify_chain([])
    assert is_valid is True
    assert err is None
