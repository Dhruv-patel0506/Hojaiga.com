# Natural Intelligence (NI) - brief 2: what we are really building, how it learns, and whether it is worth it

Version 1, 14 November 2026. This brief is a companion to `NI_VISION_BRIEF.md`:
- **Brief 1** holds the vision and the governing mathematics.
- **Brief 2** answers the practical questions:
  - Is it trained? On what data? On a GPU or a CPU?
  - How is it different from Claude and other agents, and from their feedback buttons?
  - Does it throw away the "bad" examples?
  - Is it worth building?
  - Who would buy it?

Contents
- 0. Prompt to paste first
- 1. Straight answers
- 2. What is actually built today: training, data and hardware
- 3. NI in the company picture: the management layer for AI workers
- 4. How Claude and other agents answer today, and what NI does instead
- 5. Human feedback: Claude's rating question vs NI
- 6. How NI learns: supervised, unsupervised, reinforcement, and why the bad examples are kept
- 7. The A/B choice ("which answer do you prefer?") and how NI goes further
- 8. Is it worth building? An honest assessment
- 9. Market: who needs it, the niche, and how it scales
- 10. The pitch
- 11. Questions still open

---

## 0. Prompt to paste first

```
You are my co-architect for "Natural Intelligence" (NI). Read NI_VISION_BRIEF.md (vision + mathematics)
and this brief 2 (build reality, learning, market) before answering.
Rules: understand the scenario before proposing; state components as math or measurements;
separate BUILT AND MEASURED from PROPOSED; no claim without a held-out test; be blunt about
funding risk. Help me decide what to build next so that every week produces evidence an investor
would accept.
```

---

## 1. Straight answers

| Question | Answer |
|---|---|
| Is NI a statistical model? | **Yes.** Every part that exists today is statistical learning: probability estimates, ensembles, calibrated scores. There are no hand-written rules deciding outcomes. |
| Does it need training? | **Yes, but small and fast.** It trains small models (seconds to minutes each), not a large language model. Frozen pretrained encoders, made by others, turn raw data into numbers. NI trains only the parts on top. |
| GPU or CPU? | **Both, chosen automatically.** The encoders run on the GPU (RTX 3050, 6 GB) to turn data into vectors. The small learners train on the GPU when the feature file is large and on the CPU otherwise. Graphs, the tree learner and the trust gate run on the CPU. Nothing needs a data-centre GPU. |
| What data does it train on? | **Two kinds.** (1) **46 public labelled datasets** (text, image, audio, video, graph). These are a proving ground for the outer and inner brains, not the product's real data. (2) **Real agent outcomes**: 143 of my own automation runs, plus about 40,000 public coding-agent runs. This second kind is the product's real data, and there is too little of it. |
| Is it a router or a harness? | **No.** A harness lets agents talk to each other (a chat room). NI is the layer that decides whether an agent's next decision should happen, and learns from the result. |
| Is it the same as Claude's "how is this session going?" rating? | **No.** That rating goes back to the vendor in aggregate. NI's feedback changes its trust in a specific agent, for a specific kind of task, at once and locally, and it relies mainly on real outcomes rather than opinions. |
| Does it throw away bad examples? | **No.** Failures are its most valuable data. The inner brain literally cannot learn without the outer brain's mistakes. |
| Is it worth building? | **Possibly. It has not been proven yet.** The need is real and growing, but the space is getting crowded and the key number (predicting agent success on public data) is still at chance. Section 8 gives a regret-minimising plan with clear stop rules. |
| Niche? | **Developers and teams who run several AI coding agents.** Outcomes there are cheap to verify (tests pass or fail) and the pain is immediate. Enterprise agent governance and the "human understanding" product come later. |

---

## 2. What is actually built today: training, data and hardware

### 2.1 The parts, and how each one learns

| Part | What it is | Does it train? | How | Hardware |
|---|---|---|---|---|
| Encoders | Frozen pretrained networks by others: MiniLM and BGE (text), DINOv2 (image), AST, Whisper and CLAP (audio), VideoMAE and X-CLIP (video). Graph fingerprints are computed by formula | **No.** Used as-is | Turn raw data into a vector once per dataset | GPU |
| Logic predictor | Gaussian naive Bayes and Linear Discriminant Analysis | Yes, **closed form**: means and covariances, no gradient descent | One pass of statistics | GPU or CPU |
| Pattern predictor | Small neural network (one hidden layer of 512), averaged over several seeds | Yes, **gradient descent** (AdamW) | Mini-batches | GPU for large sets, CPU for small |
| Verifier predictor | k-nearest neighbours by cosine similarity | **No weights**. It stores examples and tunes k and temperature on a held-out slice | Memory + tuning | GPU or CPU |
| Exploratory predictor | Random Fourier features with bagged linear heads, plus (v4) a gradient-boosted tree that joins only when it beats all others | Yes: gradient descent for the heads; boosting for the tree | Bootstrap bags | GPU or CPU; tree on CPU |
| Stacking (v3) | Per-predictor temperature and weights fitted by log-loss on a calibration slice | Yes, a few parameters | Grid and optimisation | CPU |
| Inner brain | Learns "was the outer brain right?" from the pattern of the decision, then verifies low-trust cases by re-running with perturbed inputs and each predictor removed | Yes, on the **outer brain's own outcome stream** | Supervised on correct/incorrect | GPU or CPU |
| Trust gate (HTTP service) | Before an action: should this agent proceed on this goal? After: record the outcome | Yes, the same v3 stack on MiniLM text embedding plus history features | Grouped out-of-fold evaluation | CPU |
| Scheduler | Plans which dataset to encode and train next within a 4 GB GPU budget; resumes after reboot | No. It is the operations layer | - | - |

### 2.2 The data

**Proving ground (public, labelled).** These test whether the outer brain plus inner brain machinery is sound across very different kinds of input.

| Modality | Datasets |
|---|---|
| Text | 20 Newsgroups, AG News, Amazon polarity, Banking77, BBC News, DBpedia, emotion, Enron spam, IMDB, Rotten Tomatoes, SMS spam, SST-2, Yahoo Answers, Yelp polarity |
| Image | beans, cats vs dogs, CIFAR-10, CIFAR-100, DTD textures, EMNIST letters, Food-101, GTSRB traffic signs, ImageNet-100, KMNIST, Oxford pets, RESISC45, Tiny ImageNet |
| Audio | BirdCLEF top-20, CREMA-D, ESC-50, GTZAN, music genres, RAVDESS, Speech Commands |
| Video | HMDB51, Kinetics mini, UCF101 subset |
| Graph | AIDS, CSL, Deezer ego nets, IMDB-binary, ogbg-molhiv, Reddit threads, Twitch egos |

**Product data (real outcomes).** This is what NI is actually for.

| Source | Size | What a record says | Result so far |
|---|---|---|---|
| My automation runs (Hojaiga outcome ledger) | 143 goals (38 pass, 105 fail) | App, goal, pass or fail | Gate AUROC **0.82** vs 0.68 for the per-app pass rate. No safe "proceed" threshold yet |
| Public coding-agent runs (SWE-agent trajectories, converted) | about 40,000 records; 3,937 used in the evaluation | Task, agent run, whether the fix passed tests | AUROC **0.52 = chance**. Transfer to my own ledger: 0.48 |

### 2.3 What this does and does not prove

- **It proves the machinery.** Combining four kinds of predictor, calibrating them and adding a self-check gives 85.5% mean accuracy on 41 datasets. The inner brain beats raw confidence on text and image.
- **It does not prove the product.** No investor funds "85% on CIFAR". The number that matters is whether NI predicts *agent* success better than the agent's own confidence, on real tasks.
  - **Own runs:** yes (0.82 vs 0.68), but only on 143 records.
  - **Public runs:** no (0.52).
  - **Why the public result is at chance:** the gate saw only the task text, not the agent's actions, the diff or the test signals.
  - **What fixes it:** richer features, which is the next build step.

---

## 3. NI in the company picture: the management layer for AI workers

### 3.1 The picture

A company has layers: board, CEO, CFO, CTO, managers, workers, interns. Every layer is controlled by the one above it, and the people above do not do the work. They decide who does it, check it, approve the risky parts, fund it, and promote or demote based on results.

AI agents today have workers and no management. They are given permissions once and then trusted. NI is the **management system** for AI workers. It is not another worker, and it is not a chat room where workers talk.

### 3.2 Harness versus governance

| | Harness / multi-agent framework | NI |
|---|---|---|
| What it is | Agents talking to agents: one agent's output becomes another's input | A judgement layer that decides whether a decision should happen |
| Who the "manager" is | Often another language model with a role prompt ("you are the CEO") | A learned model with a measured track record for every worker |
| What the manager knows about workers | What the prompt says | Measured reliability per task type, calibration, drift, cost |
| Does it learn from results? | Usually not between runs | Yes, at every outcome |
| Does it model the human? | No | Yes: value, authority, availability (brief 1, section 5) |

**Honest note.** Hierarchical agent frameworks already exist: CrewAI's hierarchical process, MetaGPT and ChatDev (with CEO, CTO and engineer roles), and AutoGen group chats. So "nobody has built a hierarchy of agents" is not true, and an investor will say so. The defensible claim is narrower and stronger:

> In those systems the manager is another language model that is told it is a manager. It has no track record, no measured reliability, no authority model and no learning from outcomes. NI is a manager that **earns** its judgement from results.

### 3.3 What a real management system does, and NI's equivalent

| Company function | What it does | NI equivalent | Status |
|---|---|---|---|
| Hiring and onboarding | Learn what a new person is good at | Behavioural fingerprint and probing of a new agent (brief 1, section 7) | Proposed |
| Job description | Scope of the role | Allowed task regions and actions per agent | Proposed |
| Delegation of authority | Who may approve what amount | Risk classes of actions mapped to autonomy levels (below) | Proposed |
| Performance review | Track record | Capability posterior per agent per task region (L2) | Gate built; per-agent posteriors proposed |
| Promotion and demotion | More or less autonomy | Autonomy level moves with the lower confidence bound of reliability | Proposed |
| CFO and budget | Spend control | Cost term in the decision rule; budget per agent | Proposed |
| Quality and audit | Check the work | Inner brain plus verification; decision trace (L17) | Inner brain built |
| Compliance and legal | Rules that are never broken | Hard constraints (brief 1, section 6.3) | Proposed |
| Escalation to the board | Humans decide the big things | Value-of-information escalation; authority-required actions | Gate built; VOI proposed |
| Incident post-mortem | Learn from failures | Failure taxonomy and root cause (section 6.3) | Proposed |

### 3.4 Autonomy levels, earned from evidence

| Level | The agent may | Promoted when |
|---|---|---|
| 0 Intern | Suggest only. A human or NI executes | Default for a new agent or task type |
| 1 Junior | Act on read-only and reversible steps | Lower 95% bound of reliability above `tau_1` |
| 2 Worker | Act on reversible writes; NI verifies a sample | Lower bound above `tau_2`, with at least `n_min` outcomes |
| 3 Senior | Act; NI checks only flagged cases | Lower bound above `tau_3`, and no drift alarm |
| 4 Lead | May direct other agents within budget | Lower bound above `tau_4`, with human sign-off |

- **Irreversible actions** (pay, delete, send, deploy to production) **always need a human**, at every level.
- **Demotion is automatic** when the drift detector fires or the lower bound falls. This is how "right on Monday, wrong on Tuesday after a model update" gets caught.
- **Promotion rule:** `level(k, region) = max { L : LCB_95( r_k(region) ) > tau_L  and  n_k(region) >= n_min(L) }`.

### 3.5 "Superior to the AI" - what that means precisely

NI does not need to be smarter than Claude, just as a manager does not need to code better than their best engineer. It needs to be **better calibrated about when each worker is right** than the worker is about itself. That is a measurable claim: NI's AUROC beats the agent's own confidence.

Before each risky step, NI returns one of these verdicts, with reasons and numbers:
- **proceed**;
- **verify first with check X**;
- **reassign to agent Y**;
- **ask the human (here is why)**;
- **stop**.

That is how it tells the AI whether its decision is correct and what to do next.

---

## 4. How Claude and other agents answer today, and what NI does instead

**Today.** You ask Claude to write a brief. Claude reads, writes the file and gives a summary. It is one worker:
- it decides alone;
- it reports its own confidence;
- it is not checked by anything that knows its track record.

Its summary is persuasive whether or not every claim in the file is right.

**With NI.** NI does not write the brief. It governs the writing.

| Step | Claude alone | With NI above it |
|---|---|---|
| Understand | Infers what you meant | Checks intent entropy. Asks for the missing story if it is high |
| Choose who works | Claude does it | Picks the agent with the best track record for "long strategic document", or splits the work |
| Do the work | Writes the file | The chosen agent writes, **on a copy** |
| Check | Self-review, if any | Inner brain scores each claim. Unverified facts (funding figures, company names, dates) are flagged or checked by a second agent or search |
| Decide | Hands the result over | Proceed, verify, or ask you, with the reasons and numbers |
| Speak | One tone | Tone fitted to the situation, never more confident than the score |
| Learn | Nothing about you or about itself changes for the next task | Your edits, kept or undone sections, and later corrections become outcomes. Trust in that agent for that kind of task moves |

This conversation shows it. In brief 1, I had to flag by hand that the pasted research figures were not re-verified. NI would do that systematically, every time, and learn which agents' claims tend to need checking.

---

## 5. Human feedback: Claude's rating question vs NI

Claude Code sometimes asks "How is Claude doing this session?" and offers good, fine or bad. As far as I know, that rating goes to the vendor, in aggregate, to improve future products. It does not change how your current agent treats your next task.

| | Session rating (Claude and others) | NI |
|---|---|---|
| Unit | Whole session | Single decision, in its scenario |
| Signal | Your opinion: good, fine or bad | **Outcomes first** (tests pass, you keep or undo, money saved or lost). Opinions second, and structured |
| Who learns | The vendor's next model, months later | NI, locally, immediately: trust in *that* agent for *that* kind of task |
| Whose model | One model for everyone | Your posterior on top of a population prior |
| What "bad" means | One bucket | A reason: wrong fact, wrong scope, wrong tone, too slow, right but unwanted, or "I was wrong, not the AI" |
| Is the rater checked? | No | Yes. The human's own reliability per task type is tracked, so a hasty "bad" on a correct answer is weighed accordingly |
| When it asks | On a schedule | Only when the answer is worth your time (value of information, brief 1, section 5.4) |
| Explicit vs implicit | Explicit button | Mostly implicit: edits, undo, retries, time to accept, re-asking the same thing |

**In one line:** the session rating is a survey; NI's feedback is a performance-review system that also checks the reviewer.

---

## 6. How NI learns: supervised, unsupervised, reinforcement, and why the bad examples are kept

### 6.1 Which kind of learning, where

| Learning type | Where NI uses it | Built? |
|---|---|---|
| Supervised (classification) | Outer brain on labelled data; inner brain on "was it right"; trust gate on pass or fail | Built |
| Self-supervised (by others) | The frozen encoders were pretrained on unlabelled data (DINOv2, for example). NI reuses them | Used |
| Unsupervised | Clustering tasks into regions and scenarios; discovering new factors; drift detection | Proposed |
| Bayesian online learning | Capability beliefs updated by counting: O(1) per event, no retraining | Proposed (simple version inside the gate's history features) |
| Reinforcement / bandits | Which agent to call; which tone to use; when to ask | Proposed |
| Preference learning | Learning value weights from your choices between options (section 7) | Proposed |
| Causal learning | Testing "does X cause the failure?" with interventions on copies | Proposed |

### 6.2 Like/dislike training, and why NI is different

In the common pattern (reinforcement learning from human feedback):
- a liked answer pushes the model towards that kind of answer;
- a disliked answer pushes it away;
- the disliked example is then mostly used as something to avoid.

NI keeps the bad side as **knowledge**, not just as a minus sign.

### 6.3 Why the bad examples are kept and used

1. **Failures are the inner brain's teacher.** The inner brain learns "was the outer brain right?". Without wrong decisions it has nothing to learn from. This is already how it works today.
2. **Failure map, not a minus sign.** Each failure is stored with its scenario and a reason, from this taxonomy:
   - wrong fact;
   - wrong scope;
   - unsafe;
   - too slow;
   - wrong tone;
   - right but unwanted;
   - human misjudged.
   NI learns *where and why* each agent fails.
3. **Bad here, good there.** An answer rejected in one scenario may be right in another, for example a blunt tone in a crisis or a risky step in a test environment. Storing the scenario keeps that knowledge instead of erasing it.
4. **Hard negatives.** Near-misses, wrong answers that looked right, are the most informative training examples. They sharpen the boundary between right and wrong.
5. **Disagreement is data.** When the human says "bad" but the outcome was good, or the reverse, NI learns something about the human, the task and the metric. It does not average the two away.
6. **Regret.** Decisions that are undone or complained about later become delayed negative outcomes. That is the mature lesson "it looked fine at the time".
7. **Post-mortems.** Clusters of failures trigger a root-cause search (brief 1, L7): is it the agent, the task type, a model update, or missing context?

**The maths of keeping the bad.** Each experience keeps its full outcome vector and reason, instead of a reward of +1 or −1:

```
e = (x, scenario, agent, output, outcome_vector, failure_reason, human_reliability)
```

The model learns `P(failure_reason | x, scenario, agent)`, not just `P(good)`.

**What this gives NI that a like/dislike model lacks.** Like/dislike models learn what to say. NI learns **when something goes wrong, why, and for whom**. That is closer to how an experienced person matures: they remember their mistakes with their circumstances; they do not just avoid them.

---

## 7. The A/B choice ("which answer do you prefer?") and how NI goes further

Some chat products show two answers and ask which you prefer. The chosen one becomes a preference example for training the vendor's next model.

NI uses the same idea, pairwise preference with a Bradley-Terry model (brief 1, section 6.4), but goes further:

1. **Preference is checked against outcome.**
   - People often prefer the confident, pleasing answer even when it is wrong (sycophancy).
   - NI records the choice and the later outcome *separately*.
   - It learns your **taste** (what you like) and **correctness** (what works) as two different things.
   - It warns when they diverge, for example: "you usually prefer the shorter plan, but the longer one passed more often".
2. **The rejected option is kept, with the reason and the scenario.** It may be the right one next time (section 6.3).
3. **Scenario-conditional.** "You prefer B" becomes "you prefer B-like answers when the deadline is close and the stakes are low". It is not a global rule.
4. **Personal and population.** Your choices adjust your own posterior. The world's patterns form the prior.
5. **Asked only when worth it.** NI shows A/B only when it is unsure what you want and the difference matters (value of information). Other times it decides and shows its reason.
6. **Bias correction.** NI accounts for position bias (people pick the first or the longer option) and checks consistency by occasionally re-asking a swapped pair.
7. **Options from different agents.** A and B can come from different agents. Every choice then also updates the agents' track records, which a single-vendor A/B test cannot do.

---

## 8. Is it worth building? An honest assessment

### 8.1 Reasons it is worth building

- **The pain is real and growing.** Companies are deploying agents faster than they can control them. There are public incidents of agents taking destructive actions; one widely reported 2025 case is an AI coding agent deleting a production database during a code freeze.
- **Vendor-neutral judgement is a structural gap.** Anthropic, OpenAI and Google will each govern their own agents. None will rank a rival above itself.
- **Outcome data compounds.** Every governed action makes the trust model better, which is a real moat if usage grows.
- **The machinery exists.** Outer brain, inner brain, trust gate, ledger and scheduler are built and measured. Most pitches at this stage have less.

### 8.2 Reasons it might not be worth it (the regret risks)

- **Crowded and moving fast.** These categories overlap with NI (re-check before pitching; this market changes monthly):
  - **Agent observability and evaluation:** LangSmith, Arize, Galileo, Patronus.
  - **Guardrails and agent security:** Guardrails AI, Lakera, Zenity.
  - **Enterprise AI governance:** Credo AI, ServiceNow AI Control Tower, Microsoft's agent identity work.
  - **Model routers.**
  - **Hierarchical agent frameworks.**
- **Platforms can bundle it.** A cloud provider or IDE could add "agent trust scores" as a free feature.
- **The key number is not there yet.** Public agent-run AUROC is 0.52. Until NI predicts agent success better than the agent's own confidence on data that is not mine, the core claim is unproven.
- **Too few real outcomes.** 143 is not evidence an investor will accept.
- **Solo-founder risk.** YC and seed investors fund teams and traction more than architecture.
- **Scope risk.** Brief 1 has 19 layers. Building them all before having users is the most likely path to regret.

### 8.3 What investors will actually judge

1. A product people use weekly.
2. A number that improves something they care about, such as fewer failed or reverted agent runs, at the same speed.
3. Growth in users or outcomes week over week.
4. Why this team, and why now.

The mathematics (brief 1) is what makes the claim credible and defensible. It does not replace items 1 to 3.

### 8.4 A regret-minimising plan with stop rules

| Gate | Build | Evidence required to continue | If it fails |
|---|---|---|---|
| **G1 (about 2 weeks)** | Trust gate inside Claude Code and OpenCode: a pre-action hook calls `/trust`; a post-action hook posts `/outcome`. Richer features: the command or diff, the agent's stated plan, files touched, test results, history | At least 300 real outcomes from my own daily work. AUROC above both the agent's own confidence and the per-task pass rate on a held-out week | Change features once. If still at chance, the "predict before acting" idea is weak; pivot to "verify after acting" |
| **G2 (about 4 to 6 weeks)** | Free local tool for other developers: one-line install, local data, a weekly "your agents' report card" | 10 to 20 outside users, with at least 5 still using it after 3 weeks. Real stories of a bad action stopped | If nobody keeps it, the pain is not sharp enough in this niche; test the team or enterprise niche |
| **G3 (about 2 to 3 months)** | Team version: shared agent report cards, autonomy levels, audit trail | A paired comparison: fewer failed or reverted agent actions with NI on than off, at similar speed. One team willing to pay or pilot | This is the pitch evidence. Apply to YC or seed with it |

**Cost of trying.** Gate 1 costs about two weeks and no money, because everything runs locally. The regret of not testing is larger than the regret of a two-week test that fails clearly.

### 8.5 Gate 1 status (14 November 2026)

**What changed from the plan.** Waiting weeks for 300 outcomes was unnecessary. Claude Code's local transcripts already held **17,804 real tool calls** with their real results (506 failed or refused, 2.8%), from 3 October to 14 November. NI now harvests them and keeps its own copy.

**Offline result.** Models were trained on the oldest 75% of actions and tested on the newest 25% (4,451 actions, 140 failures). History features were built online, so nothing saw the future.

| Method | AUROC | AUPRC |
|---|---|---|
| Failure rate of this kind of action so far | 0.750 | 0.259 |
| Gradient-boosted trees on the same history features | 0.787 | 0.235 |
| **NI outer brain + action text** | **0.785** | **0.277** |

- **Versus the simple rates and logistic regression,** NI is clearly better: the 95% bootstrap intervals are above zero.
- **Versus gradient-boosted trees,** NI ties on AUROC (difference −0.003, interval −0.036 to +0.031). It is ahead on AUPRC, the metric that matters for rare failures, in 95% of resamples (+0.035, interval −0.006 to +0.079).
- **Gate 1 criterion is not met yet.** NI does not clearly beat every baseline.
- **Adding the agent's stated plan text did not help** (AUROC 0.760).
- **The easiest failures to catch** are harness and classifier blocks (93% caught in the riskiest 5%) and tool errors outside the shell (49%). Failed shell commands are the hard part (22%).

**Live, shadow mode.** A PreToolUse hook (async, never blocks) now sends every tool call in `D:\new_automation` to a local scorer on port 8766. The score is logged before the action runs, then joined to the real outcome. The scorer takes about 90 ms per call once warm. `cc_live_report.py` produces the forward-test numbers.

**Update, same day: recent errors and task-level outcomes added.**

*Recent-error features.* These cover the agent's last failure in the session: how long ago it happened, what kind it was, whether it was on the same tool or file, and how similar the current action is to the failed action and to its error message.
- NI improved to AUROC **0.787** and AUPRC **0.283**.
- The same numeric features also lifted the tree baseline to 0.795.
- Versus the trees: AUROC difference −0.008 (interval −0.041 to +0.025); AUPRC difference +0.040, ahead in 97% of resamples.
- **Gate 1 is still not met on AUROC.** NI is the best method on precision-recall, which is what an alert budget cares about.

*Task-level outcomes.* There are two new targets (`cc_gate_task.py`, `CC_GATE1_TASK.md`).

- **After an edit, will the next run in the same turn fail?** There are 3,364 cases, with 24 failures in the test window.
  - NI scores AUROC 0.549; the baselines score 0.41 to 0.43.
  - The interval spans zero, so there is no reliable signal yet.
- **Will the human correct or interrupt this turn?** There are 299 turns with a known outcome, with 15 bad turns in the test window.
  - NI (mean over the turn's actions) scores AUROC 0.586 and puts 7 of the 15 bad turns in its riskiest 20%. The best baseline scores 0.507.
  - The interval runs from −0.21 to +0.34, so this is direction, not proof.
- **Where turn labels come from:** a teacher (Claude) labelled 348 follow-up messages, 62 of them corrections, and interrupts and rejections count as bad. A MiniLM correction classifier labels future messages. It is weak (cross-validated AUROC 0.78, precision 0.39), so it is used only as a fallback.
- **Privacy:** human message text is never stored, only the message id, its label and its embedding.

**Next steps to pass gate 1:**
- Let the forward test reach 300 or more resolved actions with at least 30 failures.
- Let you confirm or correct the teacher's turn labels. One person's check is the cheapest large improvement to the turn target.
- Collect more bad turns. At about 25% bad, the turn target needs roughly 200 more turns before its interval can exclude zero.

Files: `cc_core.py`, `cc_harvest.py`, `cc_gate.py` (writes `CC_GATE1.md`), `cc_serve.py`, `cc_hook.py`, `cc_live_report.py` (writes `CC_GATE1_LIVE.md`). The hook lives in `D:\new_automation\.claude\settings.local.json`; delete its `hooks` block to turn it off.

### 8.6 The governor layer (14 November 2026, evening)

**What changed.** The gate scored risk; nothing *decided*. The governor now turns each live action into a verdict:
- the verdicts are **proceed**, **verify first (with the check named)**, **ask the human (with the reasons)** and **stop**;
- each verdict comes with a full decision trace;
- this is the management layer of section 3, built for the wedge only. L7 to L10, L12 to L14 and L16 stay proposed (scope risk, 8.2).

| Company function (3.3) | Built as | Evidence |
|---|---|---|
| Performance review | L2 beliefs per agent x action class, refreshed at every outcome | `REPORT_CARD.md` (weekly) |
| Promotion and demotion | Level = max{L : LCB_95 > tau_L and N >= n_min}; drift alarm demotes one level | Unit (agent x class) chosen on the validation half by the objective J |
| Compliance | `gov_policy.json` hard values; sha256 lock that only a human can re-approve | Tampered policy -> governor asks the human for everything |
| Escalation to the board | VOI rule with the human's cost rising with load | 2.1 asks per 100 actions on held-out data, all authority-required |
| Quality and audit | Trace + hash-chained ledger | Re-derivation and tamper tests pass |
| Incident post-mortem | Failure reasons kept per agent (6.3) | Failure map in `GOV_REPORT.md` |

**Honest result (`GOV_REPORT.md`).**
- **Not a better failure catcher.** At the same escalation budget, the governor catches failures about as well as a plain threshold on the calibrated gate score (recall 0.377 vs 0.403, the interval spans zero).
- **Where it wins: who gets escalated.**
  - When it escalates, the action really needed it (failed or required authority) 35% of the time, against 21% for the threshold.
  - It routes publish, delete and secret actions to the human whatever their risk score.
  - It keeps routine reads and edits away from the human.
- **The utility gain is MODELLED.** It uses the policy's own loss table. No human has answered NI yet.
- **The most useful finding was about NI itself.** Its own gate was overconfident about failures (ECE 0.131). The self-check found this and fixed it with a recalibration map. The map was adopted only after it beat the raw score on a later slice.

**Still needed for gate 1.**
- **The policy is not approved yet.** Until you run `python gov_policy.py approve`, live verdicts are `ask_human / policy_integrity`. Shadow mode also logs the verdict NI would give if the policy were approved.
- **No real data for two layers.** Human answers to NI's questions (to measure `Delta_h` and the human's accuracy) and any randomised agent choice (to test L6 on real data) do not exist yet.

Files: `gov_policy.json/.py`, `gov_beliefs.py`, `gov_decide.py`, `gov_core.py`, `gov_ledger.py`, `gov_select.py`, `gov_cow.py`, `gov_self.py`, `gov_tests.py`, `gov_eval.py` (writes `GOV_REPORT.md`), `gov_card.py` (writes `REPORT_CARD.md`). `cc_serve.py` now logs `verdict`, `verdict_if_approved` and the reasons, and serves `GET /trace`.

---

## 9. Market: who needs it, the niche, and how it scales

### 9.1 Is it needed?

**Yes, by anyone who lets AI agents take actions rather than just answer.** The need grows with three things:
- the number of agents;
- the number of vendors;
- the cost of a bad action.

A single person chatting with one AI barely needs NI. A team running Claude Code, Codex, Cursor and OpenCode on a shared codebase does.

### 9.2 The niche ladder

| Step | Who | Their pain | What NI sells them | Buyer |
|---|---|---|---|---|
| **1. Wedge** | Developers using one or more AI coding agents | Agents break things, loop, or are confidently wrong; trust is all-or-nothing | A local trust gate and weekly report card: which agent to trust for which task; stops risky steps | The developer (free) |
| 2 | Engineering teams | Many agents, many people, no shared view; reviewers flooded with agent PRs | Shared report cards, autonomy levels, audit trail, "which agent PRs need a human" | Engineering lead (paid per seat or per agent) |
| 3 | Enterprises with agent fleets (IT, ops, support) | Compliance, audit, cost, liability | Governance: delegation of authority, hard constraints, evidence for auditors | Chief information or risk officer |
| 4 | Regulated domains (finance, health) | Need calibrated, auditable decisions with humans in the loop | Escalation by value of information, decision traces | Risk and compliance |
| 5. Long term | Anyone working with AI | AI that understands *you*: your values, your tendencies, when to ask you | Personal judgement layer that travels across every AI you use | Consumer or prosumer |

**Why start with developers.** It is the "public using AI for development" you described:
- outcomes are cheap and objective (tests, reverts, build failures);
- the users are reachable and adopt tools bottom-up;
- it matches the code and data that already exist.

The human-understanding direction is step 5. It needs the trust data from steps 1 to 3 first.

### 9.3 How it scales

- **Distribution through hooks, not a new app.**
  - NI plugs into the tools people already use: Claude Code hooks (a pre-tool-use hook can block an action), OpenCode plugins, Git pre-merge checks, CI pipelines, and a Model Context Protocol (MCP) server.
  - No one has to change how they work.
- **Local first.** Data stays on the user's machine by default, which removes the privacy objection and keeps the cost near zero.
- **Opt-in shared priors (the flywheel).**
  - Users can share anonymised agent fingerprints, such as "agent X fails on database migrations".
  - Everyone gets a better starting prior.
  - More users give better priors, which brings more users.
  - This is the network effect a single vendor cannot copy.
- **Business model.** Free local tool. Paid team features: shared report cards, policies, audit, single sign-on. Enterprise governance and compliance.

### 9.4 What role the wrapper plays in the product

The "gluey wrapper" (brief 1, section 7) is the **onboarding engine**. It attaches to a new agent or tool, probes it on copies, and builds its fingerprint, so NI knows its strengths and weak spots before trusting it with real work.

In the product this becomes **"add any agent in one step"**. That is what makes NI vendor-neutral in practice, not just in principle.

---

## 10. The pitch

**One line.** AI agents are workers with no management. NI is the management layer: it learns from real outcomes which agent to trust with what, stops risky steps, and tells humans when and why they are needed.

**Sixty seconds:**
- **Problem.** Teams now run several AI agents from different vendors. Each reports its own confidence, none has a track record, and permissions are all-or-nothing. When a model update makes an agent worse, nobody notices until something breaks.
- **What NI does.** It sits above every agent like a company's management system:
  - performance reviews per agent and task type, learned from real outcomes;
  - autonomy that is earned and lost;
  - verification of risky steps;
  - escalation to a human only when the human's input is worth their time, with the reason shown.
- **The data.** It learns from failures as much as successes, and it is vendor-neutral, so it can rank any agent against any other.
- **Evidence.** On my own agent runs it predicts success better than the baseline (AUROC 0.82 vs 0.68). [Replace with the gate 1 to 3 numbers as they arrive.]
- **Wedge.** Developers using AI coding agents; then teams; then enterprise agent governance.

**What not to say:**
- "consciousness";
- "deterministic";
- "nobody has built a hierarchy of agents";
- any market-size figure without a bottom-up calculation.

---

## 11. Questions still open (for the user)

1. **Product name.** "Natural Intelligence" clashes with an existing funded company (nisys.ai).
2. **Wedge.** Confirm wedge A, developers with coding agents, or choose another.
3. **Team.** Solo, or looking for a co-founder? This matters for YC.
4. **Gate 1 scope.** Which agents to hook first: Claude Code, OpenCode, or both?
5. **Your component list** still needs mapping into brief 1, section 10.
