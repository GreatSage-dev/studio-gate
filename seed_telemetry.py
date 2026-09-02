import os
import random
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
import clickhouse_connect

# 1. Load configuration securely
load_dotenv()

host = os.getenv("CLICKHOUSE_HOST")
port = int(os.getenv("CLICKHOUSE_PORT", "8443"))
user = os.getenv("CLICKHOUSE_USER", "default")
password = os.getenv("CLICKHOUSE_PASSWORD")
database = os.getenv("CLICKHOUSE_DATABASE", "default")
secure = os.getenv("CLICKHOUSE_SECURE", "True").lower() == "true"

if not password or not host:
    raise ValueError("Missing CLICKHOUSE_HOST or CLICKHOUSE_PASSWORD in environment.")

client = clickhouse_connect.get_client(
    host=host,
    port=port,
    username=user,
    password=password,
    database=database,
    secure=secure
)

# 2. Schema with explicit duration_sec column
client.command("""
CREATE TABLE IF NOT EXISTS render_telemetry (
    node_id LowCardinality(String),
    job_type LowCardinality(String),
    duration_sec Float32,
    gpu_cost_per_sec Float64,
    power_draw_kw Float32,
    timestamp DateTime64(3)
) ENGINE = MergeTree()
ORDER BY (job_type, timestamp);
""")

# Clean table before seeding
client.command("TRUNCATE TABLE IF EXISTS render_telemetry")

# 3. Generate 50,000 telemetry rows with variable durations
print("Generating 50,000 telemetry events...")
nodes = [f"node-gpu-{i:02d}" for i in range(1, 17)]
job_types = ["nerf_reconstruction", "4k_plate_upscale", "volumetric_denoise", "unreal_comp"]

NUM_ROWS = 50000

# Explicit UTC timezone awareness ensures perfect match with ClickHouse now()
end_time = datetime.now(timezone.utc)

avg_duration = (0.5 + 3.5) / 2          # midpoint of the random range = 2.0s
avg_step_ms = avg_duration * 40         # ~80ms per row on average
total_span_seconds = (NUM_ROWS * avg_step_ms) / 1000

base_time = end_time - timedelta(seconds=total_span_seconds)

rows = []
current_time = base_time

for _ in range(NUM_ROWS):
    duration = round(random.uniform(0.5, 3.5), 2)
    current_time += timedelta(milliseconds=int(duration * 40))

    job = random.choice(job_types)
    node = random.choice(nodes)

    base_rate = 0.0045 if "nerf" in job else 0.0028
    burn_per_sec = round(base_rate + random.uniform(-0.0005, 0.0015), 5)
    power_kw = round(random.uniform(0.35, 0.85), 2)

    rows.append([node, job, duration, burn_per_sec, power_kw, current_time])

print(f"Data spans from {rows[0][5]} to {rows[-1][5]}")
print(f"Last row timestamp vs now: {(datetime.now(timezone.utc) - rows[-1][5]).total_seconds():.1f} seconds ago")

# 4. Streamed insert
client.insert(
    'render_telemetry',
    rows,
    column_names=['node_id', 'job_type', 'duration_sec', 'gpu_cost_per_sec', 'power_draw_kw', 'timestamp']
)

print(f"Successfully inserted {len(rows)} telemetry rows into ClickHouse.")

# 5. Self-check: run the actual rolling-burn query right now, before the demo does
print("\nRunning self-check against the live 1-hour rolling burn query...")
result = client.query("""
    SELECT
        round(sum(gpu_cost_per_sec * duration_sec), 2) AS rolling_burn_usd,
        round(avg(power_draw_kw), 2) AS avg_power_kw,
        count() AS total_samples
    FROM render_telemetry
    WHERE timestamp >= now() - INTERVAL 1 HOUR;
""")

row = result.result_rows[0]
print(f"rolling_burn_usd = {row[0]}")
print(f"avg_power_kw     = {row[1]}")
print(f"total_samples    = {row[2]}")

if row[2] == 0:
    print("\n[WARNING] 0 samples in the last hour. The demo query will return nothing.")
    print("   Check that your data's timestamps actually reach the current time.")
else:
    print("\n[SUCCESS] Self-check passed -- the live query returns real data!")
