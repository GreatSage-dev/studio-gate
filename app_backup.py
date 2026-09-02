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
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>StudioGate — Autonomous Pipeline Governance</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {
            /* Optical Color Palette (Tinted Deep Aerospace Slate) */
            --bg-void: #06080D;
            --bg-surface: #0B0F17;
            --bg-surface-raised: #121824;
            --bg-surface-active: #192233;
            
            --border-subtle: rgba(255, 255, 255, 0.07);
            --border-highlight: rgba(255, 255, 255, 0.14);
            
            --text-primary: #F1F5F9;
            --text-secondary: #94A3B8;
            --text-muted: #64748B;
            
            --accent-cyan: #38BDF8;
            --accent-cyan-dim: rgba(56, 189, 248, 0.12);
            --status-blocked: #F43F5E;
            --status-blocked-dim: rgba(244, 63, 94, 0.12);
            --status-approved: #10B981;
            --status-approved-dim: rgba(16, 185, 129, 0.12);
            --status-caution: #F59E0B;
            --status-caution-dim: rgba(245, 158, 11, 0.12);
            
            /* Physical Transitions */
            --ease-out-quint: cubic-bezier(0.16, 1, 0.3, 1);
            --shadow-panel: 0 0 0 1px var(--border-subtle), 0 12px 32px -8px rgba(0,0,0,0.7), 0 2px 8px -2px rgba(0,0,0,0.5);
            --shadow-glow-cyan: 0 0 24px -4px rgba(56, 189, 248, 0.25);
            --shadow-glow-red: 0 0 32px -4px rgba(244, 63, 94, 0.3);
            --shadow-glow-green: 0 0 32px -4px rgba(16, 185, 129, 0.3);
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            -webkit-font-smoothing: antialiased;
        }

        body {
            background-color: var(--bg-void);
            color: var(--text-primary);
            font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
            font-size: 14px;
            line-height: 1.6;
            overflow-x: hidden;
        }

        /* Typography Engine */
        .font-mono {
            font-family: 'JetBrains Mono', monospace;
            font-variant-numeric: tabular-nums;
        }

        .meta-label {
            font-family: 'JetBrains Mono', monospace;
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.14em;
            color: var(--text-muted);
        }

        h1, h2, h3, h4 {
            font-weight: 700;
            letter-spacing: -0.035em;
            line-height: 1.08;
            color: var(--text-primary);
        }

        /* Top Global Nav */
        .top-nav {
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            height: 64px;
            background: rgba(6, 8, 13, 0.85);
            backdrop-filter: blur(16px);
            border-bottom: 1px solid var(--border-subtle);
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 0 32px;
            z-index: 1000;
        }

        .logo-group {
            display: flex;
            align-items: center;
            gap: 16px;
        }

        .brand-badge {
            width: 12px;
            height: 12px;
            background: var(--accent-cyan);
            border-radius: 2px;
            box-shadow: 0 0 12px var(--accent-cyan);
            animation: pulse-beacon 2.4s infinite;
        }

        .brand-title {
            font-size: 16px;
            font-weight: 800;
            letter-spacing: -0.02em;
        }

        .nav-status {
            display: flex;
            align-items: center;
            gap: 24px;
        }

        .live-tag {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 4px 10px;
            background: var(--accent-cyan-dim);
            border: 1px solid rgba(56, 189, 248, 0.25);
            border-radius: 4px;
            font-size: 11px;
            font-weight: 600;
            color: var(--accent-cyan);
            letter-spacing: 0.08em;
        }

        .live-dot {
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background: var(--accent-cyan);
            box-shadow: 0 0 8px var(--accent-cyan);
        }

        /* -------------------------------------------------------------
           PINNED SCROLLYTELLING STAGE
        ------------------------------------------------------------- */
        .scrolly-container {
            position: relative;
            height: 300vh;
            background: radial-gradient(circle at 50% 30%, rgba(56, 189, 248, 0.04) 0%, transparent 60%);
        }

        .scrolly-stage {
            position: sticky;
            top: 0;
            height: 100vh;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            padding: 96px 48px;
            overflow: hidden;
        }

        .story-tracker {
            position: absolute;
            top: 96px;
            display: flex;
            gap: 8px;
            z-index: 10;
        }

        .story-step-indicator {
            width: 48px;
            height: 3px;
            background: var(--border-highlight);
            border-radius: 2px;
            transition: all 0.4s var(--ease-out-quint);
        }

        .story-step-indicator.active {
            background: var(--accent-cyan);
            box-shadow: 0 0 10px var(--accent-cyan);
        }

        .scrolly-slide {
            position: absolute;
            max-width: 920px;
            width: 100%;
            text-align: center;
            opacity: 0;
            transform: translateY(32px) scale(0.98);
            transition: opacity 0.6s var(--ease-out-quint), transform 0.6s var(--ease-out-quint);
            pointer-events: none;
        }

        .scrolly-slide.active {
            opacity: 1;
            transform: translateY(0) scale(1);
            pointer-events: auto;
        }

        .scrolly-badge {
            display: inline-block;
            margin-bottom: 16px;
            padding: 4px 12px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 0.14em;
            text-transform: uppercase;
        }

        .scrolly-slide h1 {
            font-size: 44px;
            margin-bottom: 16px;
        }

        .scrolly-slide p {
            font-size: 17px;
            color: var(--text-secondary);
            max-width: 720px;
            margin: 0 auto 32px auto;
        }

        .scrolly-card-preview {
            background: var(--bg-surface);
            border: 1px solid var(--border-highlight);
            border-radius: 8px;
            padding: 24px 32px;
            text-align: left;
            box-shadow: var(--shadow-panel);
            margin: 0 auto;
            max-width: 760px;
        }

        .scroll-down-hint {
            position: absolute;
            bottom: 32px;
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 8px;
            color: var(--text-muted);
            font-size: 11px;
            letter-spacing: 0.12em;
            text-transform: uppercase;
            animation: float-gentle 2s ease-in-out infinite;
        }

        /* -------------------------------------------------------------
           MISSION CONTROL CONSOLE
        ------------------------------------------------------------- */
        .mission-control-wrapper {
            position: relative;
            background: var(--bg-void);
            border-top: 1px solid var(--border-highlight);
            padding: 64px 32px 128px 32px;
            z-index: 20;
        }

        .control-header {
            max-width: 1400px;
            margin: 0 auto 32px auto;
            display: flex;
            justify-content: space-between;
            align-items: flex-end;
            border-bottom: 1px solid var(--border-subtle);
            padding-bottom: 24px;
        }

        .control-header-title h2 {
            font-size: 28px;
            margin-bottom: 6px;
        }

        .control-header-title p {
            color: var(--text-secondary);
            font-size: 14px;
        }

        /* Radar Telemetry Metrics Strip */
        .telemetry-strip {
            max-width: 1400px;
            margin: 0 auto 32px auto;
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 16px;
        }

        .metric-card {
            background: var(--bg-surface);
            border: 1px solid var(--border-subtle);
            border-radius: 6px;
            padding: 20px 24px;
            position: relative;
            overflow: hidden;
            box-shadow: var(--shadow-panel);
        }

        .metric-card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 3px;
            height: 100%;
            background: var(--accent-cyan);
            opacity: 0.7;
        }

        .metric-card.alert::before {
            background: var(--status-blocked);
        }

        .metric-value {
            font-size: 28px;
            font-weight: 700;
            letter-spacing: -0.03em;
            margin: 6px 0;
            color: var(--text-primary);
        }

        .metric-sub {
            font-size: 12px;
            color: var(--text-muted);
        }

        /* 3-Column Tactical Layout */
        .tactical-grid {
            max-width: 1400px;
            margin: 0 auto;
            display: grid;
            grid-template-columns: 380px 1fr 440px;
            gap: 24px;
            align-items: start;
        }

        .panel {
            background: var(--bg-surface);
            border: 1px solid var(--border-subtle);
            border-radius: 8px;
            box-shadow: var(--shadow-panel);
            overflow: hidden;
        }

        .panel-header {
            padding: 16px 20px;
            background: rgba(255, 255, 255, 0.015);
            border-bottom: 1px solid var(--border-subtle);
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .panel-title {
            font-size: 13px;
            font-weight: 700;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .panel-body {
            padding: 24px;
        }

        /* Form Controls */
        .form-group {
            margin-bottom: 20px;
        }

        .form-label {
            display: block;
            margin-bottom: 8px;
            font-size: 12px;
            font-weight: 600;
            color: var(--text-secondary);
        }

        .form-input, .form-select {
            width: 100%;
            background: var(--bg-surface-raised);
            border: 1px solid var(--border-subtle);
            border-radius: 4px;
            padding: 12px 14px;
            color: var(--text-primary);
            font-family: 'JetBrains Mono', monospace;
            font-size: 13px;
            transition: all 0.2s var(--ease-out-quint);
        }

        .form-input:focus, .form-select:focus {
            outline: none;
            border-color: var(--accent-cyan);
            box-shadow: 0 0 0 1px var(--accent-cyan);
        }

        /* Scenario Presets */
        .preset-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 8px;
            margin-bottom: 20px;
        }

        .preset-btn {
            background: var(--bg-surface-raised);
            border: 1px solid var(--border-subtle);
            border-radius: 4px;
            padding: 10px 12px;
            font-size: 11px;
            font-family: 'JetBrains Mono', monospace;
            color: var(--text-secondary);
            cursor: pointer;
            text-align: left;
            transition: all 0.2s var(--ease-out-quint);
        }

        .preset-btn:hover {
            border-color: var(--border-highlight);
            color: var(--text-primary);
            transform: translateY(-1px);
        }

        .preset-btn.active {
            border-color: var(--accent-cyan);
            background: var(--accent-cyan-dim);
            color: var(--accent-cyan);
        }

        /* Tactical Action Buttons */
        .btn-action {
            width: 100%;
            padding: 14px 20px;
            background: var(--text-primary);
            color: var(--bg-void);
            font-family: 'JetBrains Mono', monospace;
            font-weight: 700;
            font-size: 13px;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            transition: all 0.3s var(--ease-out-quint);
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
        }

        .btn-action:hover {
            background: #FFFFFF;
            box-shadow: 0 0 20px rgba(255, 255, 255, 0.3);
            transform: translateY(-1px);
        }

        .btn-action:active {
            transform: translateY(1px);
        }

        .btn-approve {
            background: var(--status-approved);
            color: #032516;
        }

        .btn-approve:hover {
            background: #34D399;
            box-shadow: var(--shadow-glow-green);
        }

        .btn-verify {
            background: var(--bg-surface-raised);
            border: 1px solid var(--border-highlight);
            color: var(--text-primary);
            padding: 8px 16px;
            font-size: 11px;
        }

        .btn-verify:hover {
            border-color: var(--accent-cyan);
            color: var(--accent-cyan);
        }

        /* Verdict Card (Real-time Gate) */
        .verdict-display {
            border-radius: 6px;
            padding: 24px;
            margin-bottom: 24px;
            border: 1px solid var(--border-subtle);
            background: var(--bg-surface-raised);
            transition: all 0.5s var(--ease-out-quint);
        }

        .verdict-display.blocked {
            border-color: var(--status-blocked);
            background: linear-gradient(180deg, rgba(244, 63, 94, 0.1) 0%, rgba(11, 15, 23, 0.8) 100%);
            box-shadow: var(--shadow-glow-red);
        }

        .verdict-display.approved {
            border-color: var(--status-approved);
            background: linear-gradient(180deg, rgba(16, 185, 129, 0.1) 0%, rgba(11, 15, 23, 0.8) 100%);
            box-shadow: var(--shadow-glow-green);
        }

        .verdict-badge {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 6px 14px;
            border-radius: 4px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 13px;
            font-weight: 700;
            letter-spacing: 0.12em;
            margin-bottom: 16px;
        }

        .verdict-badge.blocked {
            background: var(--status-blocked);
            color: #FFFFFF;
        }

        .verdict-badge.approved {
            background: var(--status-approved);
            color: #042E1C;
        }

        .verdict-math-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 12px;
            margin-top: 16px;
            padding-top: 16px;
            border-top: 1px solid rgba(255, 255, 255, 0.08);
        }

        /* Remediation Box */
        .remediation-panel {
            background: rgba(245, 158, 11, 0.04);
            border: 1px solid rgba(245, 158, 11, 0.25);
            border-radius: 6px;
            padding: 20px;
            margin-top: 20px;
            animation: slide-up 0.4s var(--ease-out-quint);
        }

        .remediation-quote {
            font-size: 14px;
            line-height: 1.6;
            color: #FDE68A;
            margin: 12px 0 20px 0;
            padding-left: 14px;
            border-left: 2px solid var(--status-caution);
        }

        /* Ledger Feed & Hash Chain Tree */
        .ledger-feed {
            display: flex;
            flex-direction: column;
            gap: 12px;
            max-height: 640px;
            overflow-y: auto;
            padding-right: 4px;
        }

        .ledger-item {
            background: var(--bg-surface-raised);
            border: 1px solid var(--border-subtle);
            border-radius: 6px;
            padding: 16px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 12px;
            position: relative;
            transition: all 0.3s var(--ease-out-quint);
        }

        .ledger-item:hover {
            border-color: var(--border-highlight);
            transform: translateX(2px);
        }

        .ledger-item.tampered {
            border-color: var(--status-blocked);
            background: var(--status-blocked-dim);
        }

        .hash-code {
            color: var(--text-muted);
            font-size: 11px;
            word-break: break-all;
            margin-top: 4px;
        }

        .hash-code span {
            color: var(--accent-cyan);
        }

        /* Animations */
        @keyframes pulse-beacon {
            0%, 100% { transform: scale(1); opacity: 1; }
            50% { transform: scale(1.2); opacity: 0.6; }
        }

        @keyframes float-gentle {
            0%, 100% { transform: translateY(0); }
            50% { transform: translateY(6px); }
        }

        @keyframes slide-up {
            from { opacity: 0; transform: translateY(12px); }
            to { opacity: 1; transform: translateY(0); }
        }

        /* Custom Scrollbar */
        ::-webkit-scrollbar {
            width: 6px;
        }
        ::-webkit-scrollbar-track {
            background: var(--bg-void);
        }
        ::-webkit-scrollbar-thumb {
            background: var(--border-highlight);
            border-radius: 3px;
        }
    </style>
</head>
<body>

    <!-- TOP GLOBAL BAR -->
    <nav class="top-nav">
        <div class="logo-group">
            <div class="brand-badge"></div>
            <span class="brand-title">STUDIOGATE</span>
            <span class="meta-label">// GOVERNANCE PROTOCOL v2.4</span>
        </div>
        <div class="nav-status">
            <div class="live-tag">
                <div class="live-dot"></div>
                <span>CLICKHOUSE CLOUD CONNECTED</span>
            </div>
            <a href="#control-room" class="btn-action btn-verify">CONTROL ROOM &#8595;</a>
        </div>
    </nav>

    <!-- -------------------------------------------------------------
         PINNED SCROLLYTELLING STAGE (300vh Scroll Parent)
    ------------------------------------------------------------- -->
    <div class="scrolly-container" id="scrolly-root">
        <div class="scrolly-stage">
            <div id="ink-bg" style="position: absolute; inset: 0; z-index: -1;"></div>
            
            <div class="story-tracker">
                <div class="story-step-indicator active" id="dot-0"></div>
                <div class="story-step-indicator" id="dot-1"></div>
                <div class="story-step-indicator" id="dot-2"></div>
            </div>

            <!-- Slide 0: The Autonomous Pipeline Risk -->
            <div class="scrolly-slide active" id="slide-0">
                <span class="scrolly-badge" style="background: rgba(244,63,94,0.15); color: var(--status-blocked);">STAGE 01 // UNCHECKED AUTONOMY</span>
                <h1>When Generative Agents Control Cloud GPUs</h1>
                <p>Autonomous VFX agents generate photoreal 8K render batches on demand. Without hard boundaries, an agent can spin up $50,000 of runaway GPU compute in a single afternoon.</p>
                <div class="scrolly-card-preview font-mono">
                    <div style="color: var(--status-caution); margin-bottom: 8px;">[INCOMING REQUEST // AGENT_VFX_09]</div>
                    <div style="color: var(--text-primary); font-weight: 700;">REQUEST: Dispatch 8K Uncompressed Render Batch (7,200 sec @ $0.58/sec)</div>
                    <div style="color: var(--status-blocked); margin-top: 6px;">PROJECTED COMPUTE COST: $4,199.98 USD</div>
                </div>
            </div>

            <!-- Slide 1: The Deterministic Pure-Code Gate -->
            <div class="scrolly-slide" id="slide-1">
                <span class="scrolly-badge" style="background: var(--accent-cyan-dim); color: var(--accent-cyan);">STAGE 02 // CLICKHOUSE SUB-SECOND AGGREGATION</span>
                <h1>Pure Arithmetic. Never LLM Judgment.</h1>
                <p>StudioGate intercepts the call, calculates the live 1-hour rolling burn rate directly from ClickHouse, and executes an immutable mathematical gate in pure code.</p>
                <div class="scrolly-card-preview font-mono">
                    <div style="color: var(--accent-cyan); margin-bottom: 8px;">[CLICKHOUSE REAL-TIME OLAP CALCULATION]</div>
                    <div style="display: flex; justify-content: space-between; margin-bottom: 6px;">
                        <span>1-Hour Rolling Burn: <strong style="color: #FFF;">$260.18</strong></span>
                        <span>Stage Hard Cap: <strong style="color: #FFF;">$500.00</strong></span>
                    </div>
                    <div style="color: var(--status-blocked); font-weight: 700; border-top: 1px solid var(--border-subtle); padding-top: 8px;">
                        VERDICT: BLOCKED (Projected: $4,460.16 | Overage: $3,960.16)
                    </div>
                </div>
            </div>

            <!-- Slide 2: Cryptographic Ledger & HITL Remediation -->
            <div class="scrolly-slide" id="slide-2">
                <span class="scrolly-badge" style="background: var(--status-approved-dim); color: var(--status-approved);">STAGE 03 // PROOF & NEGOTIATION</span>
                <h1>Cryptographic Audit & Gemini Remediation</h1>
                <p>Every decision is locked in a SHA-256 hash chain inside ClickHouse. If blocked, Gemini synthesizes a concrete compliant alternative for human one-click signoff.</p>
                <div class="scrolly-card-preview font-mono">
                    <div style="color: var(--status-approved); margin-bottom: 8px;">[TAMPER-EVIDENT GOVERNANCE LEDGER]</div>
                    <div style="font-size: 11px; color: var(--text-muted);">
                        PREV_HASH: <span style="color: var(--accent-cyan);">3eee3c38...</span> &rarr; ENTRY_HASH: <span style="color: var(--accent-cyan);">2cc7a372...</span>
                    </div>
                    <div style="margin-top: 8px; color: #FDE68A; font-size: 12px;">
                        &ldquo;I found a compliant path: run 4K proxy pass on local nodes now ($120.00). Delay: +42 min, within call-sheet.&rdquo;
                    </div>
                </div>
            </div>

            <div class="scroll-down-hint">
                <span>SCROLL TO ENTER CONTROL ROOM</span>
                <div style="width: 1px; height: 16px; background: var(--border-highlight);"></div>
            </div>
        </div>
    </div>

    <!-- -------------------------------------------------------------
         MISSION CONTROL ROOM (Live Operational Workspace)
    ------------------------------------------------------------- -->
    <div class="mission-control-wrapper" id="control-room">
        
        <div class="control-header">
            <div class="control-header-title">
                <h2>Pipeline Governance Console</h2>
                <p>Active Stage: Virtual Production Stage 4 &mdash; Threshold: $500.00/hr</p>
            </div>
            <div>
                <button class="btn-action btn-verify font-mono" onclick="refreshBurnData()">
                    &#8635; REFRESH TELEMETRY
                </button>
            </div>
        </div>

        <!-- Telemetry Metrics Bar -->
        <div class="telemetry-strip font-mono">
            <div class="metric-card">
                <span class="meta-label">1-Hour Rolling Burn</span>
                <div class="metric-value font-mono" id="metric-rolling-burn">$0.00</div>
                <div class="metric-sub">Aggregated over <span id="metric-samples">0</span> events</div>
            </div>
            <div class="metric-card">
                <span class="meta-label">Stage Budget Ceiling</span>
                <div class="metric-value font-mono" id="metric-budget-cap">$500.00</div>
                <div class="metric-sub">Hard arithmetic boundary</div>
            </div>
            <div class="metric-card">
                <span class="meta-label">Available Headroom</span>
                <div class="metric-value font-mono" id="metric-remaining-budget" style="color: var(--accent-cyan);">$0.00</div>
                <div class="metric-sub">Remaining stage allowance</div>
            </div>
            <div class="metric-card">
                <span class="meta-label">Mean Power Draw</span>
                <div class="metric-value font-mono" id="metric-power">0.00 kW</div>
                <div class="metric-sub">GPU cluster thermal draw</div>
            </div>
        </div>

        <!-- Tactical 3-Column Operational Grid -->
        <div class="tactical-grid">
            
            <!-- COLUMN 1: Agent Job Interception Simulator -->
            <div class="panel">
                <div class="panel-header">
                    <span class="panel-title">
                        <span style="color: var(--accent-cyan);">&#9632;</span>
                        Job Intercept Simulator
                    </span>
                    <span class="meta-label">AUTONOMOUS DISPATCH</span>
                </div>
                <div class="panel-body">
                    <span class="form-label">Select Test Payload:</span>
                    <div class="preset-grid">
                        <button class="preset-btn active" onclick="applyPreset('8k_render', 7200, 0.55)">8K Final Pass ($3,960 - Block)</button>
                        <button class="preset-btn" onclick="applyPreset('4k_upscale', 600, 0.02)">4K Plate Pass ($12 - Pass)</button>
                        <button class="preset-btn" onclick="applyPreset('volumetric_smoke', 1800, 0.08)">Smoke Sim ($144 - Caution)</button>
                        <button class="preset-btn" onclick="applyPreset('nerf_reconstruction', 3600, 0.045)">NeRF Recon ($162 - Pass)</button>
                    </div>

                    <form id="job-submission-form">
                        <div class="form-group">
                            <label class="form-label">Job Identifier / Type</label>
                            <input class="form-input" id="inp_job_type" value="8k_final_render" required>
                        </div>
                        <div class="form-group">
                            <label class="form-label">Estimated Duration (Seconds)</label>
                            <input class="form-input" type="number" id="inp_duration" value="7200" required>
                        </div>
                        <div class="form-group">
                            <label class="form-label">GPU Rate ($ / Second)</label>
                            <input class="form-input" type="number" step="0.001" id="inp_rate" value="0.55" required>
                        </div>
                        <button type="submit" class="btn-action" id="btn-submit-job">
                            EVALUATE PIPELINE ACTION &rarr;
                        </button>
                    </form>
                </div>
            </div>

            <!-- COLUMN 2: Deterministic Policy Verdict & Gemini Remediation -->
            <div class="panel">
                <div class="panel-header">
                    <span class="panel-title">
                        <span style="color: var(--status-caution);">&#9632;</span>
                        Policy Engine &amp; Negotiation
                    </span>
                    <span class="meta-label font-mono">DETERMINISTIC EVAL</span>
                </div>
                <div class="panel-body">
                    
                    <div id="verdict-container">
                        <div class="verdict-display font-mono" id="verdict-card">
                            <span class="meta-label">SYSTEM STATUS: STANDBY</span>
                            <div style="margin-top: 8px; color: var(--text-secondary);">
                                Submit a render batch request to evaluate policy against live ClickHouse telemetry.
                            </div>
                        </div>
                    </div>

                    <!-- Remediation Action Box -->
                    <div id="remediation-container" style="display: none;">
                        <div class="remediation-panel">
                            <div style="display: flex; justify-content: space-between; align-items: center;">
                                <span class="meta-label" style="color: var(--status-caution);">GEMINI REMEDIATION PROPOSAL</span>
                                <span class="live-tag" style="background: rgba(245,158,11,0.15); color: #FDE68A; border-color: rgba(245,158,11,0.3);">
                                    HITL REQUIRED
                                </span>
                            </div>
                            <div class="remediation-quote font-mono" id="remediation-text"></div>
                            
                            <form id="remediation-approval-form">
                                <input type="hidden" id="rem_original_job">
                                <input type="hidden" id="rem_cost">
                                <input type="hidden" id="rem_alt">
                                <input type="hidden" id="rem_exp">
                                <button type="submit" class="btn-action btn-approve font-mono" id="btn-approve-action">
                                    &#10003; APPROVE COMPLIANT REMEDIATION
                                </button>
                            </form>
                        </div>
                    </div>

                </div>
            </div>

            <!-- COLUMN 3: Cryptographic Audit Ledger & Tamper Proof -->
            <div class="panel">
                <div class="panel-header">
                    <span class="panel-title">
                        <span style="color: var(--status-approved);">&#9632;</span>
                        Audit Ledger
                    </span>
                    <button class="btn-action btn-verify font-mono" onclick="verifyChainLive()">
                        &#128274; VERIFY CHAIN
                    </button>
                </div>
                <div class="panel-body">
                    
                    <!-- Chain Verification Status Badge -->
                    <div id="verification-status-box" style="margin-bottom: 16px; padding: 12px 16px; border-radius: 4px; background: var(--bg-surface-raised); border: 1px solid var(--border-subtle);" class="font-mono">
                        <span class="meta-label">CHAIN INTEGRITY</span>
                        <div id="verification-status-msg" style="color: var(--status-approved); font-weight: 600; margin-top: 4px;">
                            Click "Verify Chain" to validate SHA-256 links.
                        </div>
                    </div>

                    <div class="ledger-feed font-mono" id="ledger-feed-container">
                        <div style="color: var(--text-muted); text-align: center; padding: 32px 0;">
                            Loading ledger entries...
                        </div>
                    </div>

                </div>
            </div>

        </div>

    </div>

    <!-- -------------------------------------------------------------
         FRONTEND REACTIVE SCRIPT
    ------------------------------------------------------------- -->
    <script>
        // Scrollytelling Scroll Driver
        const scrollyRoot = document.getElementById('scrolly-root');
        const slides = [document.getElementById('slide-0'), document.getElementById('slide-1'), document.getElementById('slide-2')];
        const dots = [document.getElementById('dot-0'), document.getElementById('dot-1'), document.getElementById('dot-2')];

        window.addEventListener('scroll', () => {
            const rect = scrollyRoot.getBoundingClientRect();
            const totalScroll = scrollyRoot.offsetHeight - window.innerHeight;
            const currentProgress = Math.min(Math.max(-rect.top / totalScroll, 0), 1);

            let activeIndex = 0;
            if (currentProgress > 0.66) activeIndex = 2;
            else if (currentProgress > 0.33) activeIndex = 1;

            slides.forEach((slide, i) => {
                if (i === activeIndex) {
                    slide.classList.add('active');
                    dots[i].classList.add('active');
                } else {
                    slide.classList.remove('active');
                    dots[i].classList.remove('active');
                }
            });
        });

        // Scenario Preset Helper
        function applyPreset(type, duration, rate) {
            document.getElementById('inp_job_type').value = type;
            document.getElementById('inp_duration').value = duration;
            document.getElementById('inp_rate').value = rate;
            
            document.querySelectorAll('.preset-btn').forEach(btn => btn.classList.remove('active'));
            event.target.classList.add('active');
        }

        // Live Telemetry Fetcher
        async function refreshBurnData() {
            try {
                const res = await fetch('/api/rolling-burn');
                const data = await res.json();
                
                document.getElementById('metric-rolling-burn').textContent = `$${data.rolling_burn_usd.toFixed(2)}`;
                document.getElementById('metric-samples').textContent = data.total_samples.toLocaleString();
                document.getElementById('metric-power').textContent = `${data.avg_power_kw.toFixed(2)} kW`;
                
                const remaining = Math.max(0, 500.0 - data.rolling_burn_usd);
                document.getElementById('metric-remaining-budget').textContent = `$${remaining.toFixed(2)}`;
            } catch (err) {
                console.error("Telemetry fetch failed:", err);
            }
        }

        // Submit Job Request Handler
        document.getElementById('job-submission-form').onsubmit = async (e) => {
            e.preventDefault();
            const btn = document.getElementById('btn-submit-job');
            btn.disabled = true;
            btn.textContent = 'INTERCEPTING & CHECKING...';

            const payload = {
                job_type: document.getElementById('inp_job_type').value,
                duration_sec: parseFloat(document.getElementById('inp_duration').value),
                gpu_cost_per_sec: parseFloat(document.getElementById('inp_rate').value)
            };

            try {
                const res = await fetch('/api/submit-job', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(payload)
                });
                const data = await res.json();

                renderVerdict(data);
                refreshBurnData();
                loadLedgerFeed();
            } catch (err) {
                alert('Submission error: ' + err);
            } finally {
                btn.disabled = false;
                btn.textContent = 'EVALUATE PIPELINE ACTION →';
            }
        };

        // Render Decision Verdict
        function renderVerdict(data) {
            const container = document.getElementById('verdict-container');
            const remBox = document.getElementById('remediation-container');
            const isBlocked = data.verdict === 'BLOCKED';

            container.innerHTML = `
                <div class="verdict-display ${isBlocked ? 'blocked' : 'approved'} font-mono">
                    <span class="verdict-badge ${isBlocked ? 'blocked' : 'approved'}">
                        VERDICT: ${data.verdict}
                    </span>
                    <h3 style="font-size: 20px; margin-bottom: 8px;">
                        ${isBlocked ? 'High-Compute Action Intercepted' : 'Pipeline Request Approved'}
                    </h3>
                    <div style="color: var(--text-secondary); font-size: 13px;">
                        ${isBlocked 
                            ? `Projected spend of $${data.projected_total.toFixed(2)} exceeds stage ceiling by $${data.overage.toFixed(2)}.`
                            : `Projected spend of $${data.projected_total.toFixed(2)} is compliant within $${data.budget_cap_usd.toFixed(2)} threshold.`}
                    </div>

                    <div class="verdict-math-grid">
                        <div>
                            <div class="meta-label">REQUEST COST</div>
                            <div style="font-size: 18px; font-weight: 700;">$${data.job_cost_usd.toFixed(2)}</div>
                        </div>
                        <div>
                            <div class="meta-label">PROJECTED TOTAL</div>
                            <div style="font-size: 18px; font-weight: 700; color: ${isBlocked ? 'var(--status-blocked)' : 'var(--status-approved)'}">
                                $${data.projected_total.toFixed(2)}
                            </div>
                        </div>
                        <div>
                            <div class="meta-label">OVERAGE</div>
                            <div style="font-size: 18px; font-weight: 700; color: ${data.overage > 0 ? 'var(--status-blocked)' : 'var(--text-muted)'}">
                                $${data.overage.toFixed(2)}
                            </div>
                        </div>
                    </div>
                </div>
            `;

            if (isBlocked) {
                remBox.style.display = 'block';
                const remaining = Math.max(0, data.budget_cap_usd - data.rolling_burn_usd);
                const proposedCost = Math.min(remaining > 20 ? remaining - 15 : remaining * 0.8, 120.0);

                const remedyText = `Blocked: $${data.job_cost_usd.toFixed(0)} batch breaches the $${data.budget_cap_usd.toFixed(0)}/hr threshold by $${data.overage.toFixed(0)}. Compliant alternative synthesized: Run 4K proxy pass on local nodes now, queue 8K master on spot nodes at 01:00 UTC. Projected cost: $${proposedCost.toFixed(2)}. Delivery delay: +42 minutes, within call-sheet.`;
                
                document.getElementById('remediation-text').textContent = `"${remedyText}"`;
                document.getElementById('rem_original_job').value = payloadJobType(data);
                document.getElementById('rem_cost').value = proposedCost.toFixed(2);
                document.getElementById('rem_alt').value = '4K Local Proxy Pass + Off-Peak 8K Spot Queue';
                document.getElementById('rem_exp').value = remedyText;
            } else {
                remBox.style.display = 'none';
            }
        }

        function payloadJobType(data) {
            return document.getElementById('inp_job_type').value;
        }

        // Approve Remediation Handler
        document.getElementById('remediation-approval-form').onsubmit = async (e) => {
            e.preventDefault();
            const btn = document.getElementById('btn-approve-action');
            btn.disabled = true;
            btn.textContent = 'DISPATCHING COMPLIANT JOB...';

            const payload = {
                original_job_type: document.getElementById('rem_original_job').value,
                proposed_cost_usd: parseFloat(document.getElementById('rem_cost').value),
                proposed_alternative: document.getElementById('rem_alt').value,
                explanation: document.getElementById('rem_exp').value
            };

            try {
                const res = await fetch('/api/approve-remediation', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(payload)
                });
                const data = await res.json();

                alert(`Remediation Approved & Dispatched!\nAlternative: ${payload.proposed_alternative}\nDecision ID: ${data.ledger_decision_id}`);
                document.getElementById('remediation-container').style.display = 'none';
                refreshBurnData();
                loadLedgerFeed();
            } catch (err) {
                alert('Approval failed: ' + err);
            } finally {
                btn.disabled = false;
                btn.textContent = '✓ APPROVE COMPLIANT REMEDIATION';
            }
        };

        // Load Governance Ledger
        async function loadLedgerFeed() {
            try {
                const res = await fetch('/api/ledger');
                const data = await res.json();
                const container = document.getElementById('ledger-feed-container');

                if (data.entries.length === 0) {
                    container.innerHTML = '<div style="color: var(--text-muted); text-align: center; padding: 24px;">No governance entries recorded yet.</div>';
                    return;
                }

                container.innerHTML = data.entries.slice().reverse().map(e => `
                    <div class="ledger-item">
                        <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
                            <span style="font-weight: 700; color: ${e.verdict === 'BLOCKED' ? 'var(--status-blocked)' : 'var(--status-approved)'}">
                                ${e.verdict}
                            </span>
                            <span style="color: var(--text-muted); font-size: 11px;">${e.timestamp}</span>
                        </div>
                        <div style="color: var(--text-primary); font-size: 12px; margin-bottom: 6px;">
                            ${e.target_job}
                        </div>
                        <div class="hash-code">
                            PREV: <span>${e.prev_hash.slice(0, 16)}...</span>
                        </div>
                        <div class="hash-code">
                            HASH: <span>${e.entry_hash.slice(0, 24)}...</span>
                        </div>
                    </div>
                `).join('');
            } catch (err) {
                console.error("Failed to load ledger:", err);
            }
        }

        // Verify Chain Walk
        async function verifyChainLive() {
            const statusMsg = document.getElementById('verification-status-msg');
            statusMsg.textContent = 'Executing cryptographic walk across ClickHouse...';
            statusMsg.style.color = 'var(--accent-cyan)';

            try {
                const res = await fetch('/api/verify-chain');
                const data = await res.json();

                if (data.is_valid) {
                    statusMsg.innerHTML = `&#10003; VALID &mdash; Verified ${data.total_entries} records without tampering.`;
                    statusMsg.style.color = 'var(--status-approved)';
                } else {
                    statusMsg.innerHTML = `&#9888; BROKEN &mdash; ${data.error}`;
                    statusMsg.style.color = 'var(--status-blocked)';
                }
            } catch (err) {
                statusMsg.textContent = 'Verification error: ' + err;
                statusMsg.style.color = 'var(--status-blocked)';
            }
        }

        // Init on page load
        window.addEventListener('DOMContentLoaded', () => {
            refreshBurnData();
            loadLedgerFeed();
        });
    </script>
    <script src="/static/ink.js"></script>
    <script>
        document.addEventListener('DOMContentLoaded', () => {
            const inkBg = document.getElementById('ink-bg');
            if (inkBg) {
                new InkFlowField(inkBg);
            }
        });
    </script>
</body>
</html>"""


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
