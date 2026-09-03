"""StudioGate — Policy-Gated Governance Agent for Autonomous Media Pipelines.

Full Mission Control Interface & Scrollytelling Stage.
Built with Elite CSS/HTML Architecture & direct ClickHouse + Gemini integration.
"""
import json
import os
import traceback

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn

from studiogate import clickhouse_client, policy_engine
from studiogate.hash_chain import verify_chain
from studiogate.remediation import format_remediation_prompt, generate_live_remediation

from fastapi.staticfiles import StaticFiles

load_dotenv()

HARD_BUDGET_CAP = float(os.getenv("HARD_BUDGET_CAP_USD", "500.0"))

app = FastAPI(title="StudioGate", description="Mission Control Governance Console")
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.on_event("startup")
async def startup():
    """Ensure ClickHouse governance table exists on startup."""
    try:
        clickhouse_client.create_governance_ledger_table()
    except Exception as e:
        print(f"Warning on startup: {e}")


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/rolling-burn")
async def get_rolling_burn():
    """Query live rolling 1-hour telemetry aggregation from ClickHouse Cloud."""
    try:
        burn_data = clickhouse_client.get_rolling_burn()
        return JSONResponse(burn_data)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/submit-job")
async def submit_job(request: Request):
    """Intercept render job, execute deterministic arithmetic check, and record to ledger."""
    try:
        body = await request.json()
        job_type = body.get("job_type", "unnamed_render")
        duration_sec = float(body.get("duration_sec", 1800))
        gpu_cost_per_sec = float(body.get("gpu_cost_per_sec", 0.015))

        # 1. Fetch live ClickHouse aggregation
        burn_data = clickhouse_client.get_rolling_burn()

        # 2. Pure arithmetic job cost calculation
        job_cost = policy_engine.compute_job_cost(duration_sec, gpu_cost_per_sec)

        # 3. Pure code deterministic verdict (Zero LLM hallucination risk)
        result = policy_engine.evaluate_policy(
            rolling_burn_usd=burn_data["rolling_burn_usd"],
            requested_job_cost_usd=job_cost,
            hard_budget_cap_usd=HARD_BUDGET_CAP,
        )

        # 4. Hash-chained ledger insertion
        ledger_entry = clickhouse_client.write_ledger_entry(
            target_job=f"{job_type} ({duration_sec}s @ ${gpu_cost_per_sec}/s)",
            rolling_burn_usd=burn_data["rolling_burn_usd"],
            policy_threshold_usd=HARD_BUDGET_CAP,
            verdict=result["verdict"],
            policy_result=result,
        )

        # 5. Build structured remediation context via Gemini 3.6 Flash if BLOCKED
        remediation_context = None
        if result["verdict"] == "BLOCKED":
            remediation_context = generate_live_remediation(
                job_type=job_type,
                original_cost=job_cost,
                overage=result["overage"],
                rolling_burn=burn_data["rolling_burn_usd"],
                budget_cap=HARD_BUDGET_CAP,
                avg_power_kw=burn_data["avg_power_kw"],
            )

        return JSONResponse({
            "verdict": result["verdict"],
            "projected_total": result["projected_total"],
            "overage": result["overage"],
            "rolling_burn_usd": burn_data["rolling_burn_usd"],
            "job_cost_usd": job_cost,
            "budget_cap_usd": HARD_BUDGET_CAP,
            "avg_power_kw": burn_data["avg_power_kw"],
            "total_samples": burn_data["total_samples"],
            "ledger_decision_id": ledger_entry["decision_id"],
            "ledger_entry_hash": ledger_entry["entry_hash"],
            "prev_hash": ledger_entry["prev_hash"],
            "remediation_context": remediation_context,
        })

    except Exception as e:
        return JSONResponse({"error": str(e), "traceback": traceback.format_exc()}, status_code=500)


@app.post("/api/approve-remediation")
async def approve_remediation(request: Request):
    """Operator one-click approval: Re-evaluate policy deterministically and write dispatch entry."""
    try:
        body = await request.json()
        burn_data = clickhouse_client.get_rolling_burn()
        proposed_cost = float(body.get("proposed_cost_usd", 0.0))

        # Re-run pure arithmetic check on alternative cost
        result = policy_engine.evaluate_policy(
            rolling_burn_usd=burn_data["rolling_burn_usd"],
            requested_job_cost_usd=proposed_cost,
            hard_budget_cap_usd=HARD_BUDGET_CAP,
        )

        if result["verdict"] == "BLOCKED":
            return JSONResponse({
                "status": "REMEDIATION_STILL_BLOCKED",
                "message": f"Proposed alternative (${proposed_cost:.2f}) still exceeds the budget cap.",
                **result,
            })

        alternative = body.get("proposed_alternative", "Optimized Spot Proxy")
        explanation = body.get("explanation", "Operator approved remediation.")
        remedy_text = f"APPROVED ALTERNATIVE: {alternative}. {explanation}"

        ledger_entry = clickhouse_client.write_ledger_entry(
            target_job=f"REMEDIATION: {body.get('original_job_type', '?')} -> {alternative}",
            rolling_burn_usd=burn_data["rolling_burn_usd"],
            policy_threshold_usd=HARD_BUDGET_CAP,
            verdict="APPROVED_REMEDIATION",
            policy_result=result,
            remedy_suggestion=remedy_text,
        )

        return JSONResponse({
            "status": "DISPATCHED",
            "verdict": "APPROVED_REMEDIATION",
            "projected_total": result["projected_total"],
            "proposed_cost_usd": proposed_cost,
            "ledger_decision_id": ledger_entry["decision_id"],
            "ledger_entry_hash": ledger_entry["entry_hash"],
            "prev_hash": ledger_entry["prev_hash"],
        })

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/ledger")
async def get_ledger():
    """Fetch complete chronological ledger records."""
    try:
        ledger = clickhouse_client.read_full_ledger()
        formatted = []
        for entry in ledger:
            formatted.append({
                "decision_id": str(entry.get("decision_id", "")),
                "timestamp": str(entry.get("timestamp", "")),
                "target_job": entry.get("target_job", ""),
                "rolling_burn_usd": entry.get("rolling_burn_usd", 0),
                "policy_threshold_usd": entry.get("policy_threshold_usd", 0),
                "verdict": entry.get("verdict", ""),
                "remedy_suggestion": entry.get("remedy_suggestion", ""),
                "prev_hash": str(entry.get("prev_hash", "")),
                "entry_hash": str(entry.get("entry_hash", "")),
            })
        return JSONResponse({"total": len(formatted), "entries": formatted})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/verify-chain")
async def verify_chain_endpoint():
    """Cryptographically verify the entire SHA-256 chain walk."""
    try:
        ledger = clickhouse_client.read_full_ledger()
        is_valid, error = verify_chain(ledger)
        return JSONResponse({
            "is_valid": is_valid,
            "total_entries": len(ledger),
            "error": error,
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ---------------------------------------------------------------------------
# UI Architecture & HTML Response
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index():
    with open("templates/index.html", "r", encoding="utf-8") as f:
        return f.read()


@app.get("/console", response_class=HTMLResponse)
async def console():
    with open("templates/console.html", "r", encoding="utf-8") as f:
        return f.read()


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8080)
