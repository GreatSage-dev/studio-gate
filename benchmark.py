"""Benchmark runner for StudioGate.

Measures real-world ClickHouse Cloud latency for:
1. Rolling 1-hour telemetry aggregation (50,000 rows)
2. Full ledger cryptographic chain verification

Writes results to benchmark_results.json.
"""
import json
import os
import statistics
import time
from dotenv import load_dotenv
import clickhouse_connect

from studiogate import clickhouse_client
from studiogate.hash_chain import verify_chain

load_dotenv()


def wake_and_connect(max_retries: int = 5, retry_delay: float = 3.0):
    """Wake up ClickHouse Cloud instance and establish a connection."""
    print("Connecting to ClickHouse Cloud...")
    for attempt in range(1, max_retries + 1):
        try:
            client = clickhouse_client.get_client()
            # Simple ping query to wake the server
            client.command("SELECT 1")
            print(f"Connected to ClickHouse Cloud on attempt {attempt}.")
            return client
        except Exception as e:
            print(f"Attempt {attempt}/{max_retries} failed: {e}")
            if attempt < max_retries:
                print(f"Waiting {retry_delay}s before retry...")
                time.sleep(retry_delay)
            else:
                raise


def ensure_data_seeded(client):
    """Ensure render_telemetry and governance_ledger have test data."""
    # Check render_telemetry
    try:
        res = client.query("SELECT count() FROM render_telemetry")
        count = res.result_rows[0][0]
        print(f"Current render_telemetry rows: {count}")
        if count < 50000:
            print("Seeding 50,000 telemetry rows...")
            import seed_telemetry
            # re-check count
            res = client.query("SELECT count() FROM render_telemetry")
            count = res.result_rows[0][0]
            print(f"Seeded render_telemetry rows: {count}")
    except Exception as e:
        print(f"Error checking telemetry table: {e}. Running seeder...")
        import seed_telemetry

    # Ensure governance_ledger table exists and has entries
    clickhouse_client.create_governance_ledger_table(client)
    ledger = clickhouse_client.read_full_ledger(client)
    if len(ledger) < 5:
        print("Adding sample governance ledger entries for benchmark...")
        sample_jobs = [
            ("8K Final Pass", 7200, 0.58, "BLOCKED"),
            ("4K Plate Pass", 1200, 0.15, "APPROVED"),
            ("Smoke Sim", 450, 0.08, "APPROVED"),
            ("NeRF Reconstruction", 1800, 0.025, "APPROVED"),
            ("Volumetric Denoise", 900, 0.015, "APPROVED"),
        ]
        for job_name, duration, rate, verdict in sample_jobs:
            burn = clickhouse_client.get_rolling_burn(client)["rolling_burn_usd"]
            clickhouse_client.write_ledger_entry(
                target_job=f"{job_name} ({duration}s @ ${rate}/s)",
                rolling_burn_usd=burn,
                policy_threshold_usd=500.0,
                verdict=verdict,
                client=client,
            )


def benchmark_aggregation_query(client, iterations: int = 10) -> list[float]:
    """Benchmark the 1-hour rolling burn query over 50,000 telemetry rows."""
    latencies = []
    query_str = """
        SELECT
            round(sum(gpu_cost_per_sec * duration_sec), 2) AS rolling_burn_usd,
            round(avg(power_draw_kw), 2)                   AS avg_power_kw,
            count()                                         AS total_samples
        FROM render_telemetry
        WHERE timestamp >= now() - INTERVAL 1 HOUR
    """
    # Warm-up run
    client.query(query_str)

    for i in range(iterations):
        t0 = time.perf_counter()
        res = client.query(query_str)
        t1 = time.perf_counter()
        elapsed_ms = (t1 - t0) * 1000.0
        latencies.append(round(elapsed_ms, 2))
    return latencies


def benchmark_ledger_verification(client, iterations: int = 10) -> list[float]:
    """Benchmark reading and cryptographically verifying the full ledger chain."""
    latencies = []
    # Warm-up run
    ledger = clickhouse_client.read_full_ledger(client)
    verify_chain(ledger)

    for i in range(iterations):
        t0 = time.perf_counter()
        ledger = clickhouse_client.read_full_ledger(client)
        is_valid, err = verify_chain(ledger)
        t1 = time.perf_counter()
        elapsed_ms = (t1 - t0) * 1000.0
        latencies.append(round(elapsed_ms, 2))
    return latencies


def run_benchmark():
    client = wake_and_connect()
    ensure_data_seeded(client)

    print("\n--- Running 10x Rolling Burn Aggregation (50k rows) ---")
    agg_latencies = benchmark_aggregation_query(client, 10)
    for idx, lat in enumerate(agg_latencies, 1):
        print(f"Run {idx:2d}: {lat:6.2f} ms")

    print("\n--- Running 10x Full Ledger Chain Verification ---")
    ledger_latencies = benchmark_ledger_verification(client, 10)
    for idx, lat in enumerate(ledger_latencies, 1):
        print(f"Run {idx:2d}: {lat:6.2f} ms")

    results = {
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "cluster_host": os.getenv("CLICKHOUSE_HOST"),
        "telemetry_aggregation_50k_rows": {
            "iterations": len(agg_latencies),
            "latencies_ms": agg_latencies,
            "min_ms": min(agg_latencies),
            "max_ms": max(agg_latencies),
            "median_ms": round(statistics.median(agg_latencies), 2),
            "mean_ms": round(statistics.mean(agg_latencies), 2),
        },
        "ledger_chain_verification": {
            "iterations": len(ledger_latencies),
            "latencies_ms": ledger_latencies,
            "min_ms": min(ledger_latencies),
            "max_ms": max(ledger_latencies),
            "median_ms": round(statistics.median(ledger_latencies), 2),
            "mean_ms": round(statistics.mean(ledger_latencies), 2),
        }
    }

    # Print summary table
    print("\n========================================================")
    print("               STUDIOGATE BENCHMARK RESULTS             ")
    print("========================================================")
    print(f"{'Operation':<35} | {'Min (ms)':<9} | {'Median (ms)':<11} | {'Max (ms)':<9}")
    print("-" * 72)
    print(
        f"{'1-Hr Rolling Burn (50k rows)':<35} | "
        f"{results['telemetry_aggregation_50k_rows']['min_ms']:<9.2f} | "
        f"{results['telemetry_aggregation_50k_rows']['median_ms']:<11.2f} | "
        f"{results['telemetry_aggregation_50k_rows']['max_ms']:<9.2f}"
    )
    print(
        f"{'Full Ledger Chain Verification':<35} | "
        f"{results['ledger_chain_verification']['min_ms']:<9.2f} | "
        f"{results['ledger_chain_verification']['median_ms']:<11.2f} | "
        f"{results['ledger_chain_verification']['max_ms']:<9.2f}"
    )
    print("========================================================\n")

    with open("benchmark_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print("Saved results to benchmark_results.json.")


if __name__ == "__main__":
    run_benchmark()
