"""Remediation proposal structures for StudioGate.

When a render job is BLOCKED, Gemini generates a structured remediation
proposal. This module defines the data structures, prompt templates,
and live Google GenAI (Gemini) API invocation.
"""
from dataclasses import dataclass, asdict
import json
import os
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


@dataclass
class RemediationProposal:
    """A concrete alternative to a blocked render job."""

    original_job_type: str
    original_cost_usd: float
    proposed_alternative: str       # e.g. "4K proxy pass on local nodes"
    proposed_cost_usd: float        # The recalculated cost
    proposed_duration_sec: float    # Estimated duration of the alternative
    proposed_gpu_cost_per_sec: float  # GPU rate for the alternative
    time_impact: str                # e.g. "+42 minutes"
    quality_impact: str             # e.g. "4K instead of 8K"
    explanation: str                # Gemini's full narrative
    overage_usd: float              # How much the original exceeded the cap

    def to_dict(self) -> dict:
        """Convert to a plain dict for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "RemediationProposal":
        """Create from a dict."""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


def format_remediation_prompt(
    job_type: str,
    original_cost: float,
    overage: float,
    rolling_burn: float,
    budget_cap: float,
    avg_power_kw: float,
) -> str:
    """Build the prompt context that Gemini uses to generate a remediation.

    Args:
        job_type: The blocked job's type (e.g., "8k_render").
        original_cost: The blocked job's estimated cost in USD.
        overage: How much the projected total exceeds the budget cap.
        rolling_burn: Current 1-hour rolling burn in USD.
        budget_cap: The hard budget ceiling in USD.
        avg_power_kw: Current average power draw.

    Returns:
        A structured prompt string for the Gemini agent.
    """
    remaining_budget = max(0.0, budget_cap - rolling_burn)

    return f"""A render job has been BLOCKED by the deterministic policy engine.

BLOCKED JOB DETAILS:
- Job type: {job_type}
- Estimated cost: ${original_cost:.2f}
- Budget overage: ${overage:.2f}

CURRENT STATE:
- Rolling 1-hour burn: ${rolling_burn:.2f}
- Budget cap: ${budget_cap:.2f}
- Remaining budget: ${remaining_budget:.2f}
- Average power draw: {avg_power_kw:.2f} kW

YOUR TASK:
Propose ONE specific compliant alternative. You must:
1. State the violation and exact overage amount
2. Propose a specific alternative path (not vague "reduce quality")
3. Give the recalculated cost (MUST be under ${remaining_budget:.2f})
4. State the real-world tradeoff (time delay, quality change, etc.)

Format your response as a structured JSON with these fields:
- proposed_alternative: string (specific action, e.g. "Run 4K proxy pass on spot instances")
- proposed_cost_usd: number (must fit within remaining budget)
- proposed_duration_sec: number
- proposed_gpu_cost_per_sec: number
- time_impact: string (e.g. "+42 minutes")
- quality_impact: string (e.g. "4K proxy instead of 8K final")
- explanation: string (your full narrative explanation)

EXAMPLE of the level of reasoning expected:
"Blocked: ${original_cost:.0f} batch breaches the ${budget_cap:.0f}/hr threshold by ${overage:.0f}. I found a compliant alternative: run a 4K proxy pass on local nodes now, then queue the full 8K batch on off-peak spot instances at 01:00 UTC. Projected cost: $X. Delivery delay: +42 minutes, still within the 08:00 call-sheet window."
"""


def generate_live_remediation(
    job_type: str,
    original_cost: float,
    overage: float,
    rolling_burn: float,
    budget_cap: float,
    avg_power_kw: float,
) -> str:
    """Execute dynamic Gemini 3.6 Flash generation via the Google GenAI SDK.

    If GOOGLE_API_KEY is present, queries Gemini live for narrative remediation.
    Falls back gracefully to the prompt context if offline or API key missing.
    """
    prompt = format_remediation_prompt(
        job_type, original_cost, overage, rolling_burn, budget_cap, avg_power_kw
    )

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return prompt

    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=prompt,
        )
        if response and response.text:
            return response.text.strip()
    except Exception as e:
        print(f"Live Gemini invocation notice: {e}")

    return prompt
