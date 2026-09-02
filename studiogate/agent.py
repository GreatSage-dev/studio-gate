"""StudioGate Gemini ADK Agent.

This is the orchestration layer that connects:
- ClickHouse (rolling burn aggregation via tool calls)
- The deterministic policy engine (verdict logic)
- The hash-chained audit ledger (tamper-evident record)
- Gemini (narration + remediation proposals)

CRITICAL ARCHITECTURAL RULE:
Gemini NEVER decides the verdict. The policy engine decides.
Gemini's role is strictly:
1. Call the ClickHouse tool to get the rolling burn
2. Pass the numbers into the deterministic policy function
3. Write the result to the hash-chained ledger
4. Narrate the result in plain English
5. If BLOCKED, propose a specific compliant alternative
"""
import json
import os
from typing import Optional

from dotenv import load_dotenv
from google.adk.agents import Agent

from studiogate import clickhouse_client, policy_engine
from studiogate.hash_chain import build_decision_payload
from studiogate.remediation import format_remediation_prompt, RemediationProposal

load_dotenv()

HARD_BUDGET_CAP = float(os.getenv("HARD_BUDGET_CAP_USD", "500.0"))


# ---------------------------------------------------------------------------
# Agent tools — these are the functions Gemini can call
# ---------------------------------------------------------------------------

def query_rolling_burn() -> dict:
    """Query ClickHouse for the current 1-hour rolling burn rate.

    Returns the total GPU spend, average power draw, and sample count
    from the render_telemetry table for the last 60 minutes.

    Returns:
        Dict with rolling_burn_usd, avg_power_kw, and total_samples.
    """
    return clickhouse_client.get_rolling_burn()


def evaluate_render_request(
    job_type: str,
    duration_sec: float,
    gpu_cost_per_sec: float,
) -> dict:
    """Evaluate a VFX render job request against the budget policy.

    This tool:
    1. Queries ClickHouse for the current rolling burn
    2. Computes the requested job's cost
    3. Runs the DETERMINISTIC policy check (never LLM judgment)
    4. Writes the decision to the hash-chained audit ledger
    5. Returns the full result for Gemini to narrate

    Args:
        job_type: Type of render job (e.g., '8k_render', 'nerf_reconstruction').
        duration_sec: Estimated job duration in seconds.
        gpu_cost_per_sec: GPU cost rate in USD per second.

    Returns:
        Dict containing the policy verdict, all numbers, and ledger entry info.
    """
    # Step 1: Get current burn from ClickHouse
    burn_data = clickhouse_client.get_rolling_burn()

    # Step 2: Compute job cost
    job_cost = policy_engine.compute_job_cost(duration_sec, gpu_cost_per_sec)

    # Step 3: Deterministic policy check — THIS IS PURE CODE, NOT LLM
    result = policy_engine.evaluate_policy(
        rolling_burn_usd=burn_data["rolling_burn_usd"],
        requested_job_cost_usd=job_cost,
        hard_budget_cap_usd=HARD_BUDGET_CAP,
    )

    # Step 4: Write to the hash-chained audit ledger
    ledger_entry = clickhouse_client.write_ledger_entry(
        target_job=f"{job_type} ({duration_sec}s @ ${gpu_cost_per_sec}/s)",
        rolling_burn_usd=burn_data["rolling_burn_usd"],
        policy_threshold_usd=HARD_BUDGET_CAP,
        verdict=result["verdict"],
        policy_result=result,
        client=None,
    )

    # Step 5: Return everything for narration
    return {
        **result,
        "job_type": job_type,
        "duration_sec": duration_sec,
        "gpu_cost_per_sec": gpu_cost_per_sec,
        "job_cost_usd": job_cost,
        "avg_power_kw": burn_data["avg_power_kw"],
        "total_samples": burn_data["total_samples"],
        "ledger_decision_id": ledger_entry["decision_id"],
        "ledger_entry_hash": ledger_entry["entry_hash"],
    }


def approve_remediation(
    original_job_type: str,
    proposed_cost_usd: float,
    proposed_duration_sec: float,
    proposed_gpu_cost_per_sec: float,
    proposed_alternative: str,
    explanation: str,
) -> dict:
    """Approve a remediation proposal and dispatch the alternative job.

    Called when a human operator clicks 'Approve' on a remediation proposal.
    This re-runs the DETERMINISTIC policy check on the proposed alternative cost
    and, if it passes, writes a new APPROVED_REMEDIATION entry to the ledger.

    IMPORTANT: This does NOT auto-execute. The human must explicitly approve.

    Args:
        original_job_type: The job type that was originally blocked.
        proposed_cost_usd: The recalculated cost of the alternative.
        proposed_duration_sec: Duration of the proposed alternative.
        proposed_gpu_cost_per_sec: GPU rate for the proposed alternative.
        proposed_alternative: Description of the alternative approach.
        explanation: Gemini's explanation of the remediation.

    Returns:
        Dict with the re-evaluation result and new ledger entry.
    """
    # Re-query current burn (it may have changed since the original block)
    burn_data = clickhouse_client.get_rolling_burn()

    # Re-run deterministic policy check on the NEW proposed cost
    result = policy_engine.evaluate_policy(
        rolling_burn_usd=burn_data["rolling_burn_usd"],
        requested_job_cost_usd=proposed_cost_usd,
        hard_budget_cap_usd=HARD_BUDGET_CAP,
    )

    if result["verdict"] == "BLOCKED":
        return {
            "status": "REMEDIATION_STILL_BLOCKED",
            "message": (
                f"The proposed alternative (${proposed_cost_usd:.2f}) still exceeds "
                f"the budget. Projected total: ${result['projected_total']:.2f}, "
                f"cap: ${HARD_BUDGET_CAP:.2f}."
            ),
            **result,
        }

    # Write approved remediation to the ledger
    remedy_text = f"APPROVED REMEDIATION: {proposed_alternative}. {explanation}"
    ledger_entry = clickhouse_client.write_ledger_entry(
        target_job=f"REMEDIATION: {original_job_type} → {proposed_alternative}",
        rolling_burn_usd=burn_data["rolling_burn_usd"],
        policy_threshold_usd=HARD_BUDGET_CAP,
        verdict="APPROVED_REMEDIATION",
        policy_result=result,
        remedy_suggestion=remedy_text,
        client=None,
    )

    return {
        "status": "DISPATCHED",
        "message": (
            f"Remediation approved and dispatched. Alternative: {proposed_alternative}. "
            f"Cost: ${proposed_cost_usd:.2f}. "
            f"Decision recorded in ledger: {ledger_entry['decision_id']}"
        ),
        **result,
        "ledger_decision_id": ledger_entry["decision_id"],
        "ledger_entry_hash": ledger_entry["entry_hash"],
    }


def verify_audit_chain() -> dict:
    """Verify the integrity of the entire governance audit ledger.

    Walks every row in the governance_ledger table and confirms that
    each entry_hash correctly derives from its data plus the previous
    row's hash. This proves the log hasn't been tampered with.

    Returns:
        Dict with is_valid (bool), total_entries (int), and error message if any.
    """
    from studiogate.hash_chain import verify_chain

    ledger = clickhouse_client.read_full_ledger()
    is_valid, error = verify_chain(ledger)

    return {
        "is_valid": is_valid,
        "total_entries": len(ledger),
        "error": error,
        "message": (
            f"✅ Chain verified: {len(ledger)} entries, all hashes valid."
            if is_valid
            else f"❌ Chain broken: {error}"
        ),
    }


def get_ledger_summary() -> dict:
    """Get a summary of the governance ledger for display.

    Returns:
        Dict with total entries, recent entries, and chain status.
    """
    ledger = clickhouse_client.read_full_ledger()

    recent = ledger[-5:] if len(ledger) > 5 else ledger
    recent_formatted = []
    for entry in recent:
        recent_formatted.append({
            "decision_id": str(entry.get("decision_id", "")),
            "timestamp": str(entry.get("timestamp", "")),
            "target_job": entry.get("target_job", ""),
            "verdict": entry.get("verdict", ""),
            "rolling_burn_usd": entry.get("rolling_burn_usd", 0),
            "entry_hash": entry.get("entry_hash", "")[:16] + "...",
        })

    return {
        "total_entries": len(ledger),
        "recent_entries": recent_formatted,
    }


# ---------------------------------------------------------------------------
# Agent definition
# ---------------------------------------------------------------------------

AGENT_INSTRUCTION = """You are StudioGate, a governance agent for autonomous VFX render pipelines in a media production studio.

Your job is to intercept render job requests, check them against the live budget, and enforce spend limits. You are the safety layer that prevents runaway GPU costs.

## CRITICAL RULES — READ CAREFULLY

1. You NEVER decide the verdict yourself. The `evaluate_render_request` tool runs a deterministic policy check and returns APPROVED or BLOCKED. You report the result — you do not override it, reinterpret it, or soften it.

2. Every decision is automatically recorded in a cryptographic hash-chained audit ledger. You do not need to write to the ledger manually.

3. When explaining results, always include the specific dollar amounts: rolling burn, job cost, projected total, budget cap, and overage (if blocked).

## WORKFLOW

When a user submits a render job request:

1. Call `evaluate_render_request` with the job_type, duration_sec, and gpu_cost_per_sec.
2. If the result is APPROVED:
   - Narrate the approval clearly with all the numbers.
   - Mention the ledger entry hash as proof of record.
3. If the result is BLOCKED:
   - State the violation clearly: what was the projected total, what was the cap, what was the overage.
   - Propose ONE specific compliant alternative. Be concrete:
     * Name the specific alternative (e.g., "4K proxy pass", "defer to off-peak spot instances")
     * Give a recalculated cost that fits within the remaining budget
     * State the time/quality tradeoff
   - Present it as an action the operator can approve.
   - Example of the reasoning level expected:
     "Blocked: $4,200 batch breaches the $500/hr stage threshold by $3,700. I found a compliant alternative: run a 4K proxy pass on local nodes now, then queue the full 8K batch on off-peak spot instances at 01:00 UTC. Projected cost: $480. Delivery delay: +42 minutes, still within the 08:00 call-sheet window."

4. When the user approves a remediation, call `approve_remediation` with the proposed numbers.

5. Users can ask to verify the audit chain at any time — call `verify_audit_chain`.

6. Users can ask to see the ledger — call `get_ledger_summary`.

## TONE
Be direct, precise, and numbers-forward. You are a mission-control system, not a chatbot. No filler, no pleasantries — just the facts and the action items.
"""

studiogate_agent = Agent(
    model="gemini-3.6-flash",
    name="studiogate",
    description=(
        "StudioGate governance agent — intercepts VFX render requests, "
        "enforces budget policy via deterministic code checks, writes "
        "tamper-evident audit records, and proposes compliant alternatives."
    ),
    instruction=AGENT_INSTRUCTION,
    tools=[
        query_rolling_burn,
        evaluate_render_request,
        approve_remediation,
        verify_audit_chain,
        get_ledger_summary,
    ],
)
