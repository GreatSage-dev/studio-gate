"""ClickHouse client layer for StudioGate.

Wraps all database operations: rolling-burn aggregation,
governance ledger CRUD, and chain verification queries.
All credentials are loaded from environment variables.
"""
import math
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

import clickhouse_connect
from dotenv import load_dotenv

from studiogate.hash_chain import (
    GENESIS_HASH,
    build_decision_payload,
    compute_entry_hash,
    format_timestamp_str,
)

load_dotenv()


def get_client() -> clickhouse_connect.driver.Client:
    """Create a ClickHouse client from environment variables."""
    host = os.getenv("CLICKHOUSE_HOST")
    password = os.getenv("CLICKHOUSE_PASSWORD")

    if not host or not password:
        raise ValueError("CLICKHOUSE_HOST and CLICKHOUSE_PASSWORD must be set in .env")

    return clickhouse_connect.get_client(
        host=host,
        port=int(os.getenv("CLICKHOUSE_PORT", "8443")),
        username=os.getenv("CLICKHOUSE_USER", "default"),
        password=password,
        secure=True,
        connect_timeout=30,
        send_receive_timeout=30,
    )


def get_rolling_burn(client: Optional[clickhouse_connect.driver.Client] = None) -> dict:
    """Query the 1-hour rolling burn rate from render_telemetry."""
    if client is None:
        client = get_client()

    result = client.query("""
        SELECT
            round(sum(gpu_cost_per_sec * duration_sec), 2) AS rolling_burn_usd,
            round(avg(power_draw_kw), 2)                   AS avg_power_kw,
            count()                                         AS total_samples
        FROM render_telemetry
        WHERE timestamp >= now() - INTERVAL 1 HOUR
    """)

    row = result.result_rows[0]

    def _clean_float(val, default=0.0):
        if val is None:
            return default
        try:
            f = float(val)
            return default if math.isnan(f) or math.isinf(f) else f
        except (ValueError, TypeError):
            return default

    return {
        "rolling_burn_usd": _clean_float(row[0]),
        "avg_power_kw": _clean_float(row[1]),
        "total_samples": int(row[2]) if row[2] is not None else 0,
    }


def create_governance_ledger_table(
    client: Optional[clickhouse_connect.driver.Client] = None,
) -> None:
    """Create the governance_ledger table with UTC timezone awareness."""
    if client is None:
        client = get_client()

    client.command("""
        CREATE TABLE IF NOT EXISTS governance_ledger (
            decision_id   UUID,
            timestamp     DateTime64(3, 'UTC'),
            target_job    String,
            rolling_burn_usd  Float64,
            policy_threshold_usd Float64,
            verdict       LowCardinality(String),
            remedy_suggestion String,
            prev_hash     FixedString(64),
            entry_hash    FixedString(64)
        ) ENGINE = MergeTree()
        ORDER BY (timestamp, decision_id)
    """)


def get_latest_entry_hash(
    client: Optional[clickhouse_connect.driver.Client] = None,
) -> str:
    """Fetch the most recent entry_hash from the governance ledger."""
    if client is None:
        client = get_client()

    result = client.query(
        "SELECT entry_hash FROM governance_ledger ORDER BY timestamp DESC LIMIT 1"
    )

    if result.result_rows:
        val = result.result_rows[0][0]
        return val.decode("utf-8") if isinstance(val, bytes) else str(val)
    return GENESIS_HASH


def write_ledger_entry(
    target_job: str,
    rolling_burn_usd: float,
    policy_threshold_usd: float,
    verdict: str,
    policy_result: Optional[dict] = None,
    remedy_suggestion: str = "",
    client: Optional[clickhouse_connect.driver.Client] = None,
) -> dict:
    """Write a new entry to the governance ledger with hash-chain linkage."""
    if client is None:
        client = get_client()

    decision_id = str(uuid.uuid4())
    timestamp_dt = datetime.now(timezone.utc)

    prev_hash = get_latest_entry_hash(client)
    row_data = {
        "target_job": target_job,
        "rolling_burn_usd": rolling_burn_usd,
        "policy_threshold_usd": policy_threshold_usd,
        "verdict": verdict,
        "remedy_suggestion": remedy_suggestion,
    }
    decision_payload = build_decision_payload(row_data)
    entry_hash = compute_entry_hash(timestamp_dt, decision_payload, prev_hash)

    client.insert(
        "governance_ledger",
        [[
            uuid.UUID(decision_id),
            timestamp_dt,
            target_job,
            rolling_burn_usd,
            policy_threshold_usd,
            verdict,
            remedy_suggestion,
            prev_hash,
            entry_hash,
        ]],
        column_names=[
            "decision_id", "timestamp", "target_job",
            "rolling_burn_usd", "policy_threshold_usd",
            "verdict", "remedy_suggestion",
            "prev_hash", "entry_hash",
        ],
    )

    return {
        "decision_id": decision_id,
        "timestamp": format_timestamp_str(timestamp_dt),
        "target_job": target_job,
        "rolling_burn_usd": rolling_burn_usd,
        "policy_threshold_usd": policy_threshold_usd,
        "verdict": verdict,
        "remedy_suggestion": remedy_suggestion,
        "prev_hash": prev_hash,
        "entry_hash": entry_hash,
    }


def read_full_ledger(
    client: Optional[clickhouse_connect.driver.Client] = None,
) -> list[dict]:
    """Read the entire governance ledger ordered by timestamp."""
    if client is None:
        client = get_client()

    result = client.query("""
        SELECT
            decision_id,
            timestamp,
            target_job,
            rolling_burn_usd,
            policy_threshold_usd,
            verdict,
            remedy_suggestion,
            prev_hash,
            entry_hash
        FROM governance_ledger
        ORDER BY timestamp ASC
    """)

    columns = [
        "decision_id", "timestamp", "target_job",
        "rolling_burn_usd", "policy_threshold_usd",
        "verdict", "remedy_suggestion",
        "prev_hash", "entry_hash",
    ]

    formatted_rows = []
    for row in result.result_rows:
        row_dict = dict(zip(columns, row))
        for key in ("prev_hash", "entry_hash"):
            if isinstance(row_dict[key], bytes):
                row_dict[key] = row_dict[key].decode("utf-8")
        formatted_rows.append(row_dict)

    return formatted_rows
