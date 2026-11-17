# Natural Intelligence: what I understand we are building, where I disagree, and what comes next

Version 1, 14 November 2026. Written by Claude after reading:
- `NI_VISION_BRIEF.md`;
- `NI_VISION_BRIEF_2.md`;
- the code in `natural_intelligence/`;
- your description of 14 November.

Two labels are used throughout:
- **BUILT AND MEASURED**: running on this machine, with a number from held-out data.
- **PROPOSED**: not built yet.

---

## 1. What you are building, in my words

Today every AI works alone:
- chat models (Claude, GPT, Gemini);
- agents (Claude Code, OpenCode, browser and desktop bots).

Each one answers and acts, and nothing above them knows any of these things:
- how often each one is right;
- what it is good at;
- when it changed;
- when a human must decide.

They were trained once on patterns in data, and they are confident whether or not they are right.

NI is the **intelligence above them**: one mind that stands over many workers. It is not another worker, and it is not a chat room where workers talk to each other.

It has **two layers**, like the outer and inner brain in your code:
- **The outer brain** forms a judgement: what is the answer, which agent should do this, what will happen.
- **The inner brain** judges the judgement: is that answer likely right, is this agent trustworthy *here*, is this situation one I have never seen.

Above both sits a **controller** that decides, for every step any AI wants to take, one of these:
- proceed;
- verify first;
- try another agent;
- ask the human (and say why);
- stop.

It keeps every branch of a decision alive instead of pruning the second child. It compares the branches with evidence, and recommends one with the proof attached.

It cross-questions:
- the human, when the story is incomplete;
- the agents, when they disagree.

It learns from **real outcomes**, not from GPU training runs:
- every outcome updates its beliefs in microseconds;
- failures are kept as knowledge, not thrown away.

It governs itself by the same rules it applies to the others.

**The product in one sentence:** *the management layer for AI workers: it learns from their real outcomes whom to trust with what, keeps every alternative alive until the evidence picks one, and tells humans when and why they are needed.*

---

## 2. What I learned from the two briefs

1. **The mathematics is the product.**
   - One objective: maximise scenario-weighted value minus cost.
   - It is subject to hard constraints: chance of irreversible harm at most epsilon, the original never changed, hard values never traded, human authority.
   - Nineteen layers each solve one piece of it: a belief update, a decision rule, or an invariant.
   - This framing is right. A router has a lookup table; NI has an objective, constraints and beliefs.
2. **The wedge is coding-agent governance.**
   - Outcomes there are cheap and objective: tests pass, commands fail, people undo.
   - Brief 2 warns that building all 19 layers before having users is the most likely way to fail.
3. **Bad examples are the most valuable data.**
   - Each failure is kept with its scenario and a reason.
   - The inner brain cannot learn without the outer brain's mistakes.
4. **The human is a modelled participant, not a prompt source.**
   - The human's value depends on the scenario.
   - NI asks only when the answer is worth the human's time, or when authority is required.
5. **The honest claims are:**
   - calibrated, auditable and bounded-risk;
   - **not** "deterministic", "conscious" or "nobody has done hierarchy";
   - market figures only from a bottom-up count.

---

## 3. Corrections. Please correct me back where I am wrong

| Your statement | My honest correction | Why it matters for investors |
|---|---|---|
| "It doesn't have to train like pattern training." | **It still learns from data.** Every learning system does. The difference is real but narrower: NI's beliefs are counts and small models updated **online**, one event at a time, on a CPU. There are no GPU runs and no retraining. It is statistical learning on *outcomes*, not pattern training on a corpus. | Say "learns continuously from real outcomes, no retraining", not "not trained". |
| "Even if it has never seen it, it will handle it easily without human interaction." | **No system can promise that.** What NI can do, and what can be measured: (1) **detect** that a situation is new (novelty and uncertainty); (2) handle it **safely**: probe on a copy, cross-question, act cautiously or ask; (3) learn from the outcome so it is no longer new. Handling the unknown "easily, without humans" is how agents cause damage. | "Knows when it does not know" is provable and fundable. "Handles anything" is not. |
| "Like a quantum computer, both outcomes at once." | **The right model is classical branching, not quantum superposition.** NI keeps several branches alive and evaluates them in parallel. In the real world only one irreversible action can happen, so the other branches must run on **copies** (L15) or in simulation. That is exactly what copy-on-write is for. | Do not use quantum language in a pitch. "Keeps every alternative alive and evaluates them on copies" is concrete and true. |
| "Left and right brain." | Our two layers are a **predictor** and a **metacognitive judge of the predictor**. That is closer to System 1 / System 2, or to metacognition, than to the left and right hemispheres. | Use "outer brain / inner brain" with the math. Avoid neuroscience analogies a reviewer can attack. |
| "Our own maths, not algorithms it was trained on." | **We combine well-founded mathematics, and the combination is ours.** The parts are Bayesian updating, decision theory, value of information, Shapley values, CUSUM and Thompson sampling. Inventing new mathematics is not needed and would hurt credibility. Section 5 proposes one genuinely new *measured* quantity: perspective coverage. | Reviewers trust known parts in a new composition. They distrust "new maths". |
| "Not just a governor, a brain like JARVIS or Vision." | Agreed on ambition. But the **brain's edge is judgement, not raw reasoning**. It will not out-reason Claude or GPT. It decides *which* reasoner to trust, *when*, and *what is missing*. Its "self-intelligence" is the measured track record, the beliefs and the branch evidence. | It depends on the workers. It governs them; it does not replace them (brief 1, section 3). |
| "Accuracy is not the only factor." | **Agreed, and it must still be measurable.** Section 5 turns "considers all perspectives" into a number. | An unmeasured virtue is a claim; a measured one is evidence. |

---

## 4. Built and measured vs proposed (14 November 2026)

| Piece | Status | Number |
|---|---|---|
| Outer brain (4 predictors + calibration + tree learner) | BUILT | 85.5% mean held-out accuracy on 41 public datasets |
| Inner brain ("was the outer right?") | BUILT | Beats raw confidence on text (0.88 vs 0.82) and image; loses on graphs |
| Gate on real Claude Code actions | BUILT, live shadow | AUROC 0.787 on the newest 25%; ties gradient-boosted trees, ahead on AUPRC |
| Governor: beliefs, decision, VOI, autonomy, trace, ledger, policy lock, self-check | BUILT, live shadow, **policy approved by you at 18:38** | Escalation precision 0.35 vs 0.21; failure recall ties the plain gate; NI found and fixed its own miscalibration (ECE 0.131 -> 0.007) |
| Copy-on-write sandbox | BUILT | Invariant tests pass; human-only promotion |
| Agent selection (Thompson + drift reset) | BUILT, **simulated only** | Regret 88 vs 750 for a fixed router after a simulated vendor update |
| **Branch engine: keep every child alive, prove the pick** (`gov_branch.py`) | **BUILT, offline tests only** | 7 tests pass: (1) every child kept, failures with reasons; (2) correct smallest change picked at P_best 1.0; (3) original hash unchanged; (4) a real trade-off produces a question instead of a silent pick; (5) the answer moves the pick in the stated direction; (6) a failed parent's child is still explored and can win. **Not yet run on real agent branches** |
| Cross-questioning of the human about trade-offs | BUILT inside the branch engine (most informative pairwise question) | Same offline tests. Asking about *intent* (L9) is still proposed |
| Agent-to-agent communication control; swarm control | PROPOSED | - |
| Causality, bridging unrelated A and B, values learned from choices, tone bandit, wrapper fingerprints | PROPOSED | - |
| Learning from videos | Built elsewhere in Hojaiga (harvester, Whisper, RAG); **not connected to NI** | - |

---

## 5. Your new ideas, mapped to mathematics and to a test

Each idea below is stated as a definition, a rule and a test, as brief 1 requires.

### 5.1 Keep every branch alive (the "second child")

- **Definition.** A decision node has children `b_1 ... b_m`: alternative plans, agents or answers. Each branch gets a measured value vector `v(b)`: tests passed, cost, time, size of change, risk class, reversibility.
- **Rule: never prune on a guess.**
  - A branch may be dropped only if it is **Pareto-dominated on measured values**.
  - Otherwise it stays alive.
  - With uncertain value weights `w ~ posterior` (brief 1, section 6.4), compute `P_best(b) = P_w( b = argmax w . v )`.
  - Recommend `b*` only if `P_best(b*) >= 0.8`. Otherwise show the Pareto options and cross-question (5.2).
- **Proof attached.** For every recommendation NI shows:
  - the evidence table;
  - the losing branches with their reasons;
  - the weight change that would flip the pick.
- **Test.**
  - Branch choices agree with the later outcome more often than "first branch" or "most confident agent".
  - Dropped branches are never better on the held-out check.
  - Weight-flip tests are monotone.

### 5.2 Cross-questioning

- **Of the human.** Ask when `H(intent | context) > tau(stakes)`. Choose the question that most reduces the uncertainty about **which branch is best**: the question whose answer has the highest expected information about `argmax_b`.
- **Of the agents.** When two agents disagree, ask each to defend its answer against the other's evidence, then run the disagreement on a copy.
- **Test.** Wrong inferences per question asked go down, compared with acting at once and with asking at a fixed rate.

### 5.3 Control of communication between agents, and of swarms

- **Model.** Every agent-to-agent message and every action passes through NI's bus.
- **Per channel:**
  - allowed or denied by policy;
  - a budget (messages, money, time);
  - loop detection (the same request bouncing between agents);
  - a fan-out limit (one agent starting many);
  - a kill switch.
- **A swarm is a set of agents with a shared budget.** NI allocates the budget by each agent's lower confidence bound, the same rule as autonomy levels.
- **Test.** Inject a runaway swarm (loops, fan-out, cost spikes) in simulation, then on real agents. Measure time to containment, and false containments of healthy swarms.
- **Status.** PROPOSED. It needs a real multi-agent workload. Options: OpenCode plus Claude Code on one repository, or your CrewAI organ.

### 5.4 Handling something seen for the first time

- **Novelty.**
  - `nov(x)` = distance of the action's embedding to its nearest past experience;
  - plus `n_k(region) = 0`;
  - plus outer-brain disagreement.
- **Rule.** A high novelty score lowers the earned level (already true: new kinds start at level 0). It triggers a probe on a copy before the real action, then learns from the result.
- **Test.** The failure rate on first-seen actions with NI is below the rate without NI, at similar speed.

### 5.5 "Considers all perspectives": the proposed new measured quantity

- **Perspective coverage.** After a failure, a post-mortem labels the factor that caused it, for example "file was locked", "agent ignored the error", "production environment".
  - `coverage = fraction of failures whose causal factor was already in NI's decision trace before the action`.
- **Why it is new.** No accuracy metric measures whether a judge *looked at the right things*. Coverage does.
- **How it grows (factor discovery, brief 1, section 5.2).** When post-mortems keep naming a factor NI did not have, NI proposes it as a new factor. The factor is adopted only if a paired test shows better predictions.
- **Test.** Coverage rises over time and beats the agent's own stated plan.
- **This is the number for "better than a human brain that forgets".**

### 5.6 Self-healing and self-growing, precisely

| Term | What it means precisely | Status |
|---|---|---|
| **Self-healing** | NI detects when its own parts drift or miscalibrate, and repairs them under the paired-test rule. | Built for the gate: the L18 self-check found ECE 0.131 and adopted a map only after it beat the raw score on later data |
| **Self-growing** | New factors, new task regions and new agents are added from evidence, each through a paired test. | Regions and drift: built. Factors: proposed |
| **Self-sufficient** | Runs locally, resumes at boot, needs no GPU for the judgement layer. | Built (`resume_ni.ps1`) |

### 5.7 Learning from videos

The Hojaiga harvester already turns tutorial videos into procedures. For NI, a video is **another agent's demonstration**: a source of candidate branches and of factors ("the presenter checked X before Y"). It enters through the same gate: kept only if using it improves a held-out outcome. PROPOSED.

---

## 6. What the world requires now, and what to look up online

I cannot verify these items in this session; they are from memory. Please check each one, and bring me what you find.

### 6.1 Regulation and standards (buyers will ask about these)

- **EU AI Act:**
  - Article 14, human oversight;
  - the obligations for high-risk systems;
  - the dates when they apply.
  - NI's "ask the human, with the reason" is direct evidence of oversight.
- **NIST AI Risk Management Framework** and its generative-AI profile.
- **ISO/IEC 42001**, AI management systems.
- **Banking model-risk guidance** (US SR 11-7), as the template for "probabilistic but validated".

### 6.2 Agent protocols (this is how NI plugs in)

- **MCP** (Model Context Protocol): the tool-call layer. NI can sit as an MCP proxy.
- **A2A**, Google's agent-to-agent protocol: the communication layer for 5.3.
- **OpenTelemetry semantic conventions for GenAI and agents**: the standard trace format. NI's ledger should export to it.
- **Hook systems** in Claude Code, OpenCode, Cursor and Codex: the distribution channel (brief 2, section 9.3).

### 6.3 Datasets with real agent outcomes (the product data)

- **Coding agents:** SWE-bench Verified trajectories, and the OpenHands and SWE-agent runs (one is already downloaded).
- **Tool use:** tau-bench, ToolEmu (risky tool calls with judged harm), R-Judge (safety judgements on agent records), AgentHarm.
- **Web and computer use:** WebArena, OSWorld, Mind2Web trajectories with success labels.
- **Multi-agent failures:** the "MAST" taxonomy paper (why multi-agent LLM systems fail, 2025) and its annotated traces. This is the key dataset for 5.3.
- **Incidents:** the AI Incident Database, for the cost side of irreversible actions.

### 6.4 Closest competitors to re-check (the market moves monthly)

- **Agent observability:** LangSmith, Arize, Galileo, Patronus.
- **Guardrails:** Guardrails AI, Lakera, Invariant Labs.
- **Governance:** Credo AI, ServiceNow AI Control Tower.
- **Model routers:** Not Diamond, Martian.
- **The closest idea:** AWS "graduated autonomy".

### 6.5 Research to read for the branch and cross-question parts

- Tree of Thoughts and LATS (tree search over agent steps).
- Debate and cross-examination between models.
- Active inference and expected free energy.
- Robust decision-making under weight uncertainty: Pareto sets and minimax regret.

---

## 7. What would make it much better, in order

1. **Real outcomes at scale.** Wire OpenCode, or a second agent, into the same hook. Two vendors on one repository is the minimum demo of "vendor-neutral".
2. **The branch engine on real tasks.** For a real task, have two agents (or two plans) produce branches, run both on copies, and let NI pick with proof. This is your "second child" idea, and the strongest demo.
   - This turn builds the engine and tests it offline.
   - Running real agents on tasks costs your usage, so it needs your go-ahead.
3. **Your answers.** When NI asks you, answer in one click. That is the only way to measure the human's value `Delta_h` and your own accuracy.
4. **Perspective coverage (5.5)** from post-mortems of real failures.
5. **Agent-to-agent bus and swarm control (5.3)** once a multi-agent workload exists.
6. **A product name** without the nisys.ai clash.

---

## 8. Built in this session (offline tests pass; no real agent branches yet)

`gov_branch.py`, the branch engine. It works like this:
1. It takes a source (file or folder), several branches (alternative transforms from any agent) and a check (a test command).
2. It runs every branch on its own copy, in parallel.
3. It measures each branch's value vector, and keeps every branch with its evidence. Losers are kept with the reason they lost.
4. It computes the Pareto front and `P_best` under uncertain weights.
5. It recommends with proof, or cross-questions with the single most informative question.
6. The original's hash is checked at every step.

**Use it from Python:**

```
rec = gov_branch.explore(src, [dict(name=..., agent=..., transform=fn, children=[...]), ...], test_cmd)
gov_branch.answer(rec, "compact", "agent_trust")
```

Records are kept in `data_user/gov/branches/`.

### First real run (14 November 2026, 19:07; `BRANCH_RUN1.md`)

**Set-up.**
- **Task:** implement `gov_coverage.py`, the perspective-coverage metric of section 5.5.
- **Hidden check:** 18 checks. The agents never saw it; a reference implementation passes 18/18 and the empty stub fails.
- **Branches:** six. Each ran on its own copy, and the original stayed unchanged.

| Branch | Result |
|---|---|
| Claude Code (headless) | **No code.** It could not authenticate: the session's gateway token gave 401, the direct route was refused |
| Claude Sonnet via OpenCode + Copilot | **No code.** Copilot rejected the configured token |
| DeepSeek, GLM, MiMo (OpenCode, free) | **18/18.** Stated confidence 88, 92, 90 |
| Nemotron (OpenCode, free) | **14/18** (quality 0.78). Rejected, with the four failing checks named |

| Policy | Pick | Hidden-check quality |
|---|---|---|
| First branch (incumbent agent) | Claude Code: nothing usable | 0 |
| Most confident agent | GLM | 1.00 |
| NI branch engine | DeepSeek, flagged equivalent to MiMo, no question asked | 1.00 |

**Two design faults found and fixed on this run.**
1. **A scaling bug.** Failed branches were included when scaling each dimension.
2. **A pointless question.** NI asked you "speed or compactness?" about differences of 0.04 s and 3 lines out of 60, which is noise.

The fix:
- measured values are rounded to their noise floor;
- the change-size floor is relative: 10% of the typical change;
- ties share P_best equally;
- NI asks only if the expected loss from just picking is above 0.05. This is the same value-of-information idea as L5.

The synthetic tests still pass: 43/43.

**What this does and does not show.**
- Executing the check on every branch avoided the failure of trusting the incumbent agent. Here the incumbent produced nothing, and Nemotron's plausible-looking code failed 4 of 18 checks.
- One task cannot show that NI beats "most confident". In this run that baseline was also right.

**Honest limit.** Except for the run above, every test uses small synthetic code tasks. The claim "branch choice beats first-branch or most-confident-agent" needs real branches from two agents on real tasks. Running agents costs your usage, so it waits for your go-ahead.

## 9. Batch run: 7 real tasks x 4 free agents (14 November 2026, 21:45)

Full record: [BRANCH_BATCH1.md](BRANCH_BATCH1.md); driver `gov_branch_batch.py`. Six new tasks (CUSUM, hash chain, Pareto, Shapley, ask budget, isotonic) plus coverage_v1 again; each hidden check proven first (reference passes fully, stub fails).

- NI shipped correct code on 7/7 tasks, never shipped a failing branch, and asked the human 0 times.
- Most confident agent: 5/7 (2 broken). Random single agent: 5.75/7 on average. Best single agent in hindsight (mimo): 7/7, same as NI.
- Strict reading: sign test vs most-confident 2 wins / 0 losses, p = 0.50; vs random agent 3 / 0, p = 0.25. Not yet significant. The bootstrap says "NI better than a random agent", but with 7 tasks that interval is optimistic.
- Stated confidence carried no information: nemotron said 95 and failed coverage; three models said 90-96 and shared the same isotonic bug (one fitted value per pooled block instead of per x).
- What NI adds is not knowing in advance which agent is best: it equalled the hindsight-best agent without being told which one that was.
- Fixed during the run: parallel OpenCode runs collide on one SQLite store ("database is locked"), so each job now gets its own data folder; hidden checks now count a crash as failing the checks that did not run.

## 10. Batch 2 and the 20-task pool (2026-11-15)

13 harder tasks x 4 free agents (BRANCH_BATCH2.md); pooled with batch 1 in BRANCH_POOLED20.md.
**Defect in the run:** 28 of 52 batch-2 agent runs hit the 900 s timeout with empty output. On 8 tasks (intervals, cmdsplit, rank, cron, diff, redact, jpath, wilson), DeepSeek, GLM and MiMo all returned nothing. Only Nemotron answered there. This was the free providers failing to respond, not the agents getting tasks wrong. The pooled 20-task numbers therefore overstate NI's lead over a single agent.
- Pooled 20 (contaminated): NI 17/20 correct, 0 broken (it refused to ship on 3 tasks with no fully passing branch, including Nemotron's 0.96 and 0.97); most confident 14/20, 4 broken; random agent 11/20. Sign test vs random 11-2, p = 0.022; vs most confident 3-2, p = 1.0.
- Clean 12 (every agent got a fair run; BRANCH_CLEAN12.md): NI 12/12, 0 broken; most confident 10/12; random 9.75/12; the best single agents 11/12. Sign test vs random 6-0, p = 0.031; vs most confident 2-0, p = 0.50.
Reading: on the clean tasks, NI beating a randomly chosen agent is now significant at p < 0.05. NI beating "trust the most confident agent" is not yet shown, because those two disagreed on only 2 tasks. Stated confidence stayed uninformative (90-97 on wrong answers). Next: rerun the 8 timed-out tasks with fewer parallel jobs and a retry.
**Cause of the timeouts (found 2026-11-15 rerun):** the batch-2 timeouts were not the providers being slow. OpenCode's free tier answered "Free usage limit reached" for DeepSeek, GLM and MiMo, and `opencode run` kept retrying silently until our 900 s timeout. The limit applies to the whole account. Nemotron still answered, which is why it was the only agent left on the last 8 tasks. A rerun with 2 workers and a retry hit the same limit, so I stopped it. Fixed in gov_branch_batch.py: NI_BATCH_WORKERS, NI_BATCH_RETRIES, and NI_BATCH_KEEP/NI_BATCH_FROM (reuse one agent's earlier results). The clean 20 needs the free limit to reset, or a different agent.

## 11. Rerun with other agents (2026-11-15, user: "Use other agents")

The 8 tasks were rerun with four other free OpenCode models: LongCat 2.5, Flint 40B, Iceman and Beam. Nemotron's earlier answers were reused (BRANCH_RERUN8.md). A run now stops within seconds when the provider says "usage limit" (opencode --print-logs). Those runs are counted as unavailable, not as wrong answers.
The new agents also ran out of free usage partway through. All four answered intervals, cmdsplit and rank; three answered cron. On diff, redact, jpath and wilson only Nemotron answered, so there was no real branching and those 4 tasks are left out.
**Fair pool, 16 tasks (BRANCH_FAIR.md):** NI 16/16 correct, 0 broken. Most confident agent 13/16 (3 broken). Random agent 13.35/16. Sign test vs random 7-0, p = 0.016. Vs most confident 3-0, p = 0.25.
New case: on cmdsplit the most confident new agent (Iceman, confidence 93) passed 92% of checks; NI picked LongCat, which passed every check.
Reading: NI beating a random agent is significant (p = 0.016). NI beating the most confident agent has gone 3 wins, 0 losses, but needs about 6 disagreements for p < 0.05. The pool mixes two agent sets, and I wrote both the tasks and the checks.
