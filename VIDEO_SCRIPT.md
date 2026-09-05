# 🎙️ StudioGate: Official Hackathon Video Demo Script

> **Target Duration:** 2:30 – 3:00 minutes  
> **Workflow:** Screen record silently first (following the **Visual Action** cues), then record this **Voiceover Narration** in post-production. You can speed-ramp or trim pauses in your editor.

---

## 🎬 Shot 1: The Problem & Domain Gap (0:00 – 0:30)

### 🖥️ Visual Action:
1. Open browser to `http://localhost:8080/console#telemetry`.
2. Mouse hovers over the **Rolling Spend hero card** ($31.94 / $500.00 Cap) and the unboxed metric strip (*ClickHouse Latency: 1.8ms*, *Cluster Power Draw*, *Active Nodes*).
3. The sample counter is visibly ticking upward in real-time from the background ClickHouse streaming daemon.

### 🎙️ Voiceover:
> "In media production and VFX pipelines, GPU spend is volatile. A runaway 8K render or misconfigured autonomous agent can burn through thousands of dollars overnight.
>
> Right now, in visual effects studios, GPU budget policy lives in a Slack message. A supervisor messages the farm operator: *'don't let this job run over $500.'* That message is the policy. It lives in Slack. It's unverifiable, unmeasurable, and forgotten by Monday morning.
>
> StudioGate makes it a cryptographic law."

---

## 🎬 Shot 2: The Architecture & Deterministic Guardrail (0:30 – 1:05)

### 🖥️ Visual Action:
1. Click the **Autonomous Dispatch Simulator** tab in the sidebar (`#simulator`).
2. Point cursor to the 3 simulated workload payloads on the left.
3. Click the top button: **"VFX_09 // 8K Volumetric Final Pass ($4,176.00)"**.
4. The system immediately intercepts the job and auto-switches to the **Remediation tab** (`#remediation`).

### 🎙️ Voiceover:
> "StudioGate implements a clean architectural separation: the **Private Layer Decides**, and the **Public Layer Executes**.
>
> Here in the Dispatch Deck, an autonomous agent requests an 8K volumetric pass costing $4,176.00. 
>
> Our private policy engine evaluates this against live ClickHouse Cloud rolling burn using pure Python arithmetic—not an LLM. Because this would breach our $500 ceiling, the job is blocked instantaneously. 
>
> Zero GPU resources consumed. Zero hallucination risk."

---

## 🎬 Shot 3: Gemini Cognitive Remediation & Real Procedural Render (1:05 – 1:45)

### 🖥️ Visual Action:
1. In the **Gemini Cognitive Remediation view** (`#remediation`):
2. Show the **Blocked Runaway Request** on the left with the rendered frame `vfx_09_blocked_pass.png` stamped with *"EXECUTION HALTED // Zero GPU Resources Burned"*.
3. Show the **Gemini Synthesized Proposal** on the right with `gemini_remedy_proxy.png`.
4. Click **"Dispatch Compliant Remedy ($180.00)"**.
5. The button pulses with the loading spinner, procedural raymarch executes in real-time, the spot node is allocated, and the green confirmation pill appears with the SHA-256 block hash!
6. Click over to the **Telemetry Hub** tab for 2 seconds to show `sim-worker-spot-01` actively rendering and burn updated.

### 🎙️ Voiceover:
> "Now, look at the remediation deck. 
>
> Gemini does not generate text around the edges of this system. It reads live financial state and produces actionable production alternatives that operators execute with one click.
>
> Gemini 3.6 Flash inspected our $500 cap, downsampled the uncompressed 8K render into a 4K proxy format with 2x temporal super-sampling, and re-routed it to spot instances at $180.00. 
>
> When I click 'Dispatch Compliant Remedy', StudioGate allocates the spot node, executes a real procedural raymarcher to generate the frame, and commits the transaction."

---

## 🎬 Shot 4: The Immutable Ledger & The Killer Falsifiability Test (1:45 – 2:35)

### 🖥️ Visual Action:
1. Click the **Immutable Cryptographic Ledger** tab (`#ledger`).
2. Scroll through the ledger items showing the timestamp, target task, SHA-256 hash, and status badges.
3. Click **"Verify Cryptographic Chain"**.
   - The top banner flashes bright green: *"Cryptographic Chain Verified: Validated 70 contiguous SHA-256 blocks with zero tampering."*
4. **THE FALSIFIABILITY TEST:**
   - Now click **"Simulate Tamper"**.
   - The top banner instantly turns crimson red:
     *"Chain Compromised! SHA-256 Mismatch: Hash mismatch at row 69 ... stored entry_hash does not match computed."*
5. Click **"Verify Cryptographic Chain"** again.
   - The banner restores to bright green.

### 🎙️ Voiceover:
> "Every decision—approved or blocked—is logged to ClickHouse Cloud in a strict SHA-256 cryptographic hash-chain.
>
> But here is StudioGate's sharpest principle: **build a verifier that can disagree with you.**
>
> If I tamper with any entry in this ledger, the verification breaks. Watch.
>
> *(Click 'Simulate Tamper')*
>
> I simulate an unauthorized change of just one character in the ledger. The independent verifier recalculates the chain walk and immediately detects the mathematical mismatch.
>
> *(Click 'Verify Cryptographic Chain')*
>
> Restore it, and the cryptographic chain is validated with zero tampering."

---

## 🎬 Shot 5: Conclusion & The Extracted Primitive (2:35 – 3:00)

### 🖥️ Visual Action:
1. Switch back to the **Telemetry Hub** showing the continuous streaming metrics, sloped hero card, and healthy cluster.
2. Quickly show the project repo showing `hashledger/` standalone package.
3. Fade to StudioGate logo / title card.

### 🎙️ Voiceover:
> "To push this further, we extracted the core hash-chaining engine into `hashledger`—a standalone, zero-dependency Python library ready for any production audit pipeline.
>
> Sub-second ClickHouse Cloud telemetry, deterministic Python guardrails, Gemini cognitive remediation, and immutable cryptographic proof.
>
> This is StudioGate: autonomous governance for the next era of agentic cinema."

---

## 💡 Editing & Post-Production Tips:
1. **Speed-Ramping:** In Shot 3, if the render takes 1-2 seconds, you can speed-ramp it by 200% so it feels lightning-fast and snappy on camera.
2. **Audio Levels:** Keep voiceover clear around -6dB, with subtle cinematic ambient tech synth music ducked to -24dB in the background.
3. **Pacing:** Let the crimson tamper moment in Shot 4 breathe for 2 seconds—it is the single most compelling verification moment judges will see.
