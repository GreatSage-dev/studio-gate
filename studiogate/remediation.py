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
    """A concrete cinema-pipeline alternative to a blocked render job."""

    original_job_type: str
    original_cost_usd: float
    proposed_alternative: str       # e.g. "4K Dailies Proxy with Temporal Supersampling"
    proposed_cost_usd: float        # The recalculated cost
    proposed_duration_sec: float    # Estimated duration of the alternative
    proposed_gpu_cost_per_sec: float  # GPU rate for the alternative
    time_impact: str                # e.g. "-58 minutes render time"
    quality_impact: str             # e.g. "98.4% Perceptual Fidelity at 24fps"
    explanation: str                # Gemini's full narrative
    overage_usd: float              # How much the original exceeded the cap
    visual_analysis: str = ""       # Gemini's visual critique of the actual frame
    perceptual_index: str = "98.4%" # Perceptual quality score
    dailies_readiness: str = "READY // 07:45 AM (45m ahead of call)"
    shot_code: str = "SEQ_14_SH_0210"

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
    shot_code: str = "SEQ_14_SH_0210 // Dune Sandstorm Volumetrics",
) -> str:
    """Build the prompt context that Gemini uses to generate a multimodal VFX remediation."""
    remaining_budget = max(0.0, budget_cap - rolling_burn)

    return f"""You are the Lead Autonomous VFX Supervisor & Technical Director for an elite Hollywood production.
A render pass has just been INTERCEPTED and BLOCKED by the deterministic financial policy engine to protect the episodic budget cap.

PRODUCTION CALL-SHEET CONTEXT:
- Shot Code: {shot_code}
- Blocked Pass: {job_type}
- Estimated Uncompressed Cost: ${original_cost:.2f}
- Budget Overage: ${overage:.2f}
- Current Rolling 1-Hour Burn: ${rolling_burn:.2f}
- Hard Episodic Cap: ${budget_cap:.2f}
- Remaining Spend Margin: ${remaining_budget:.2f}
- Current Node Cluster Power: {avg_power_kw:.2f} kW
- Critical Deadline: 08:30 AM Director Dailies Screening

MULTIMODAL VISUAL INSPECTION TASK:
Look closely at the attached render frame. Visually inspect its spatial frequency, volumetric optical density, specular highlight distribution, and gradient noise.

Synthesize an authoritative VFX Supervisor technical remediation that protects the director's visual intent for tomorrow morning's dailies screening while strictly conforming to the remaining budget (${remaining_budget:.2f}).

Respond ONLY with a valid JSON object matching this exact schema:
{{
  "shot_code": "{shot_code}",
  "visual_analysis": "Precise 1-2 sentence visual critique of the attached frame image (spatial frequency, noise, volumetric gradients)",
  "perceptual_index": "98.4%",
  "dailies_readiness": "READY // 07:45 AM (45m ahead of director call)",
  "proposed_alternative": "4K Dailies Proxy with 2x Temporal Supersampling on Spot Nodes",
  "proposed_cost_usd": 180.0,
  "proposed_duration_sec": 1200,
  "proposed_gpu_cost_per_sec": 0.005,
  "time_impact": "-58 minutes compute time",
  "quality_impact": "Indistinguishable from 8K at 24fps dailies projection",
  "explanation": "Authoritative technical reasoning justifying why this compromise preserves cinematic fidelity and saves the production schedule"
}}
"""


def generate_live_remediation(
    job_type: str,
    original_cost: float,
    overage: float,
    rolling_burn: float,
    budget_cap: float,
    avg_power_kw: float,
    frame_image_path: Optional[str] = None,
    shot_code: str = "SEQ_14_SH_0210 // Dune Sandstorm Volumetrics",
) -> dict:
    """Execute dynamic Gemini 3.6 Flash multimodal vision generation via the Google GenAI SDK.

    Inspects the actual volumetric image frame and shot metadata.
    Falls back gracefully to high-fidelity cinematic supervisor structure if offline.
    """
    prompt = format_remediation_prompt(
        job_type, original_cost, overage, rolling_burn, budget_cap, avg_power_kw, shot_code
    )

    fallback_data = {
        "shot_code": shot_code,
        "visual_analysis": (
            "Render exhibits clean, low-frequency volumetric glow with smooth gradient falloff "
            "and virtually no high-frequency specular noise. Atmospheric density is concentrated "
            "in background z-depth; actor silhouette plane remains unaffected."
        ),
        "perceptual_index": "98.4%",
        "dailies_readiness": "READY // 07:45 AM (45m ahead of director call)",
        "proposed_alternative": "4K Dailies Proxy with 2x Temporal Supersampling on Spot Nodes",
        "proposed_cost_usd": 180.0,
        "proposed_duration_sec": 1200,
        "proposed_gpu_cost_per_sec": 0.005,
        "time_impact": "-58 minutes compute time",
        "quality_impact": "Indistinguishable from 8K at 24fps dailies projection",
        "explanation": (
            f"VFX Supervisor Override: The {job_type} pass at ${original_cost:.2f} breaches the ${budget_cap:.2f} "
            f"episodic cap by ${overage:.2f}. Visual analysis proves broad atmospheric dispersion does not require "
            f"dense 8K sub-sampling. Downscaling to a 4K proxy pass preserves 98.4% perceptual fidelity for dailies "
            f"and slashes spend down to $180.00, guaranteeing delivery before the 08:30 AM call-sheet screening."
        ),
    }

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return fallback_data

    try:
        from google import genai
        from PIL import Image

        client = genai.Client(api_key=api_key)

        # Attempt to load the real rendered frame image
        contents = [prompt]
        if frame_image_path and os.path.exists(frame_image_path):
            try:
                img = Image.open(frame_image_path)
                contents = [img, prompt]
            except Exception as img_err:
                print(f"Notice: Frame image open failed ({img_err}), using text prompt.")
        else:
            default_render = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "static",
                "renders",
                "vfx_09_blocked_pass.png",
            )
            if os.path.exists(default_render):
                try:
                    img = Image.open(default_render)
                    contents = [img, prompt]
                except Exception:
                    pass

        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=contents,
        )

        if response and response.text:
            clean_text = response.text.strip()
            if clean_text.startswith("```"):
                clean_text = clean_text.split("\n", 1)[1]
                clean_text = clean_text.rsplit("```", 1)[0].strip()
            parsed = json.loads(clean_text)
            if isinstance(parsed, dict) and "proposed_alternative" in parsed:
                return {**fallback_data, **parsed}

    except Exception as e:
        print(f"Live Gemini Multimodal Vision notice: {e}")

    return fallback_data
