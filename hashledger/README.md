# ⛓️ hashledger

> **Lightweight, zero-dependency SHA-256 cryptographic hash-chaining library for immutable audit ledgers, compliance logging, and agentic governance.**

Extracted directly from [StudioGate](https://github.com/GreatSage-dev/studio-gate) — the autonomous policy-gated governance agent built for *Agentic Cinema: The Blockbuster Hackathon* (ClickHouse Partner Track).

---

## 💡 Why hashledger?

When autonomous AI agents, render farms, or automated dispatchers execute multi-thousand-dollar decisions, traditional database logs can be surreptitiously deleted, truncated, or altered. 

`hashledger` turns any standard database table (e.g. ClickHouse, PostgreSQL, SQLite) into an **append-only, mathematically tamper-evident cryptographic chain**:

$$\text{entry\_hash} = \text{SHA-256}(\text{timestamp} \parallel \text{canonical\_payload} \parallel \text{prev\_hash})$$

If an attacker or rogue script modifies a single character, timestamp, or cost metric anywhere in the ledger's history, walking the chain produces an instant, verifiable mathematical mismatch.

---

## ⚡ Features

- **Zero External Dependencies**: Implemented entirely in standard Python (`hashlib`, `json`, `datetime`).
- **Deterministic Canonical Serialization**: Eliminates key-ordering and whitespace ambiguity across heterogeneous platforms.
- **Genesis Block Anchoring**: Guaranteed 64-character hex zero-hash (`0` × 64) genesis boundary.
- **Sub-Millisecond Verification**: Verifies thousands of chained blocks in under 100 milliseconds.
- **Falsifiability & Tamper Detection**: Returns exact row indices, expected hashes, and tampered fields when breaches occur.

---

## 📦 Installation

```bash
pip install hashledger
```
*(Or vendored directly as `hashledger.py` in your project)*

---

## 🚀 Quick Example

```python
from hashledger import HashLedger, GENESIS_HASH

# 1. Initialize ledger
ledger = HashLedger()

# 2. Append decisions
entry1 = ledger.append(
    payload={"target_job": "VFX_09 8K Pass", "verdict": "BLOCKED", "cost": 4176.0},
    timestamp="2026-09-04 12:00:00.000"
)

entry2 = ledger.append(
    payload={"target_job": "4K Proxy Spot", "verdict": "APPROVED", "cost": 180.0},
    timestamp="2026-09-04 12:01:00.000"
)

# 3. Verify integrity across all blocks
is_valid, error = ledger.verify()
assert is_valid is True
print("Chain status: 100% Cryptographically Verified!")

# 4. Prove falsifiability — simulate tampering
entry1["payload"]["cost"] = 100.0  # Tampering with cost!
is_valid, error = ledger.verify()
assert is_valid is False
print(f"Tamper detected: {error}")
```

---

## 🏛️ Verification Walk Logic

```python
from hashledger import verify_chain

rows = [
    {"timestamp": "2026-09-04 12:00:00.000", "payload": {...}, "prev_hash": "000...000", "entry_hash": "a1b2..."},
    {"timestamp": "2026-09-04 12:01:00.000", "payload": {...}, "prev_hash": "a1b2...", "entry_hash": "c3d4..."},
]

is_valid, err = verify_chain(rows)
if not is_valid:
    print(f"CRITICAL: Cryptographic chain compromised at {err}")
```

---

## 📄 License

MIT License. Designed for production pipelines and autonomous AI agent architectures.
