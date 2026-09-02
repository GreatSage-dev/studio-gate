# 🎬 StudioGate — Official 3-Minute Demo Video Script

**Target Duration:** 3:00  
**Host/Track:** Google Cloud — Agentic Cinema Hackathon (ClickHouse Track)  
**Presenter:** Single speaker with live screen recording of the StudioGate Mission Control Console.

---

### **0:00 – 0:30 | The Hook & The Human Story**
* **Visual:** Close-up on the StudioGate Hero section with WebGL flow-field animation.
* **Audio / Voiceover:**
  > *"On a Friday evening, a VFX supervisor submits an 8K volumetric render batch and heads home for the weekend. By Monday morning, the job has run unchecked for 72 hours across 16 GPU nodes, and the project is $4,176 over budget with three weeks left to deliver.*
  > 
  > *In autonomous media pipelines, a single runaway script can incinerate a studio’s cloud budget in minutes. And you cannot trust a traditional LLM to govern financial safety thresholds—because LLMs hallucinate math.*
  > 
  > *StudioGate sits between the job dispatcher and the compute cluster. That batch never runs without a deterministic policy verdict. StudioGate is the gate that should have existed."*

---

### **0:30 – 0:45 | Mission Control Console Overview**
* **Visual:** Scroll down to the Mission Control Console (`#demo`). Highlight the 4 Telemetry Metric cards populating in real time from ClickHouse Cloud:
  * 1-Hour Rolling Burn
  * Hard Budget Cap ($500.00)
  * Available Headroom
  * Total Processed Jobs
* **Audio / Voiceover:**
  > *"This is the StudioGate Mission Control Console. It connects directly to ClickHouse Cloud, continuously streaming and aggregating rolling telemetry across 50,000 GPU events in under 210 milliseconds.*
  > 
  > *Every dollar of compute burn and power draw is tracked with sub-second precision."*

---

### **0:45 – 1:30 | Live Job Intercept & Deterministic Block**
* **Visual:** Click the **"Agent VFX_09 // 8K Final ($4,176.00)"** button in the Autonomous Agent Simulator sidebar.
* **Visual:** Show the red `BLOCKED` badge appear immediately in the Cryptographic Audit Ledger with its SHA-256 hash. Expand the collapsed code box showing `policy_engine.py`.
* **Audio / Voiceover:**
  > *"Let's simulate an autonomous agent dispatching an expensive 8K render pass projected at $4,176. I click submit.*
  > 
  > *Instantly, StudioGate intercepts the dispatch. The verdict is BLOCKED.*
  > 
  > *Here is the critical architectural rule: Gemini never touches the pass/fail decision. The policy engine is 100% pure Python arithmetic. The pass/fail check has zero LLM hallucination risk. The decision is instantaneously committed to our ClickHouse cryptographic ledger with its own SHA-256 block hash."*

---

### **1:30 – 2:00 | Google Gemini Intelligent Remediation**
* **Visual:** Highlight the yellow **Gemini AI Remediation** box that populated on the screen.
* **Audio / Voiceover:**
  > *"Because the job was blocked, Google Gemini 3.6 Flash kicks in via the Google Agent Development Kit—not to alter the verdict, but to solve the production bottleneck.*
  > 
  > *Gemini analyzes the remaining headroom and suggests a production-ready alternative:*
  > 
  > *'Run a 4K proxy pass on local nodes now ($180), then queue the full 8K batch on off-peak spot instances at 01:00 UTC.'*
  > 
  > *The human operator reviews the tradeoff, clicks approve, and dispatches the compliant alternative without stalling the production schedule."*

---

### **2:00 – 2:20 | Cryptographic Audit Chain Verification**
* **Visual:** Click the **"Verify Ledger Chain"** button in the bottom dark banner. An alert appears displaying: `✅ Chain Verified! Validated X contiguous cryptographic blocks.`
* **Audio / Voiceover:**
  > *"Now, let's verify the audit trail. I click 'Verify Ledger Chain.'*
  > 
  > *ClickHouse returns every historical row, and we verify the contiguous SHA-256 hash links from the genesis block to the latest entry.*
  > 
  > *Every decision StudioGate has ever made is cryptographically locked. A studio auditor or finance director can verify this chain at any time. Gemini cannot rewrite it, and rogue processes cannot tamper with it."*

---

### **2:20 – 2:40 | System Architecture (The Four Pillars)**
* **Visual:** Display the StudioGate architecture diagram.
* **Audio / Voiceover:**
  > *"StudioGate's architecture rests on four decoupled pillars:*
  > 1. **Job Dispatcher Interceptor:** Catches every media compute request before GPU allocation.
  > 2. **Deterministic Policy Engine:** Pure code evaluation that enforces hard budget caps with zero hallucinations.
  > 3. **ClickHouse Cloud:** Powers sub-second rolling telemetry aggregation across 50,000+ records and hosts the immutable audit ledger.
  > 4. **Google Gemini ADK:** Delivers cognitive remediation proposals and plain-English operator narration."*

---

### **2:40 – 3:00 | Benchmark Numbers & Closing Pitch**
* **Visual:** Display the Benchmark Results table and summary callout on screen.
* **Audio / Voiceover:**
  > *"We benchmarked StudioGate live against ClickHouse Cloud in GCP europe-west4:*
  > * 50,000-row rolling burn aggregation: **184.67ms min / 207.25ms median**
  > * Full cryptographic chain verification: **172.14ms min / 184.88ms median**
  > 
  > *$4,176 in GPU spend protected. Real-time sub-210ms query performance. Zero LLM hallucinations in the verdict loop.*
  > 
  > *This is autonomous pipeline governance for the future of cinema. Thank you."*
