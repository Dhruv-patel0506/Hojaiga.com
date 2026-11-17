# Natural Intelligence (NI) - vision brief for a new chat

Version 2, 14 November 2026. Paste this whole file into the new chat.

It contains:
- the prompt;
- the vision;
- how NI differs from today's agentic AI;
- the governing mathematics;
- the human-value model;
- the values and affect model;
- the "gluey wrapper";
- my research notes;
- what is built and measured, with the honest limits and the proof plan.

Contents
- 0. Prompt to paste first
- 1. The vision, in my words
- 2. Design principle
- 3. How NI differs from today's agentic AI (pitch section)
- 4. The governing mathematics (one objective, nineteen layers)
- 5. The human value model: which factors, which scenarios, and how the decision changes
- 6. Values and affect: what NI considers, since it cannot feel
- 7. The gluey wrapper: learning any AI's "brain" from its behaviour
- 8. Research notes and what they mean for NI
- 9. What is already built and measured
- 10. My list of components to build
- 11. Honest limits
- 12. Closest existing work
- 13. What would convince an investor (proof plan)

---

## 0. Prompt to paste first

```
You are my co-architect for "Natural Intelligence" (NI). Read the whole brief before answering.
Rules:
(1) Understand the scenario before proposing anything. Ask me for the missing story instead of guessing.
(2) The mathematics is the product. State every component as math: a definition, an update rule,
    a decision rule, the algorithm that implements it, and the test that proves it.
    Investors fund math and evidence, not consciousness language.
(3) Separate BUILT AND MEASURED from PROPOSED in every answer.
(4) Never claim a component works until a held-out test shows it beats a simple baseline.
(5) Every factor NI uses (human value, scenario, external conditions, values, tone) must be named,
    measurable, and shown to change the decision when it changes.
Task now: map my list of components (section 10) onto the governing objective and layers
(sections 4 to 7), one component at a time, each with its math, its algorithm, and its test.
```

---

## 1. The vision, in my words

**The picture.** In the Marvel story, Tony Stark's AIs (JARVIS, Vision, Ultron, FRIDAY) lived under one roof. Vision and Ultron were on opposite sides, but each simply knew the others existed and had different capabilities. AI does not feel rivalry. It only knows that another AI exists with different strengths. NI is the intelligence that lives above all of them.

**What I have.** Four or five AI models (for example Claude, Gemini, local models), plus bots (Claude Code, OpenCode, browser and desktop automation). Each is best at what it was built for.

**What NI is NOT.**
- **Not a simple converter or router** ("image goes to Gemini, orchestration goes to Claude"). That is a fixed pattern rule, and anyone can build it.
- **Not another model trained on a dataset.** Everyone can now train an algorithm on the data they are given.
- **Not a JARVIS clone** (screen plus voice plus a rented LLM brain). Those already exist on GitHub.
- **Not a robot-type brain with fixed thresholds.** Its judgement changes when the scenario changes, and it can say which factor changed it.

**What NI IS.**
1. **A governor, manager and controller** above all the AIs and bots, so they do not get out of hand.
2. **A companion, not a replacement.** It keeps humans in the loop and explains *why* the human is needed in a given situation, in measured terms, instead of praising itself.
3. **Judgement learned from experience.** It learns from what the AIs actually do and what actually happens, not only from a training dataset.
4. **Understands before acting.** It does not jump in. If the user has not given the full story, it asks for it before making an inference.
5. **Has a voice.** It uses different tones (calm, firm, playful, confident, even arrogant when that fits) and picks the right one for the scenario. Technically this is modelled affect and stance chosen from the situation. It reads feelings in the situation; it does not feel them.
6. **Connects unrelated things.** A and B may look unrelated in one frame and be related in another. NI must search for that bridge and verify it, instead of discarding the unusual pattern.
7. **The "gluey wrapper" (the Venom image).** It sticks to any AI, codebase or workflow from the back side, takes its shape and understands its architecture. It never needs the weights:
   - if the AI is open source, NI reads its structure directly;
   - if it is closed, NI learns how it functions from its behaviour.
   NI works on a **copy**. It can replicate it, speed it up or restructure it, but it never changes the original. Changes are promoted only after verification and human approval.
8. **Self-governing.** NI governs itself by the same rules it uses on others:
   - its own predictors have trust scores;
   - its own changes pass the same paired tests;
   - it cannot change its own hard constraints.
9. **Learns the "brain" from the answers.** We are not building *how to answer*. We are building a model of *how each AI and each human behaves*: what it is good at, where it fails, how it changes, what it values. It learns all of this from the answers and outcomes alone, the way a person learns a colleague's character without ever seeing their neurons.
10. **Learns from everyone's patterns.** It cannot feel, but it can see. It sees what people choose, correct, approve, reject and regret, both in this user's history and across public human behaviour. Those patterns become its values (section 6).

**Why now.** Companies are adding agents faster than they can control them. BCG reports that 35% of companies already have agentic AI in production (2026), and existing permissions were designed for humans. The same agent can be right on Monday and wrong on Tuesday after a model update (AWS, 2026). Nobody ships a learned judgement layer across many different AIs.

---

## 2. Design principle

The AIs supply **knowledge and skill**. The bots supply **hands**. NI supplies **judgement that improves with experience**:
- whom to trust;
- when to act, when to verify, and when to ask a human;
- what matters in this scenario;
- how to connect what none of them connects alone.

---

## 3. How NI differs from today's agentic AI (pitch section)

Claude, GPT and Gemini agents, and coding agents such as Claude Code and OpenCode, are **workers**. Each receives a request and produces an answer or an action, using a model trained once on internet-scale data. NI is not another worker. It is the **judgement layer** that learns, from the workers' real outcomes, which worker to trust, when, and when a human must decide.

| Dimension | Today's agentic AI (one model + tools) | NI |
|---|---|---|
| What it models | The world's text: the next token given the context | The **agents themselves**, the **human**, and the **scenario** (models of models) |
| When it learns | At training time. Frozen between releases | At **every event**. O(1) belief updates on CPU, no retraining |
| What it learns from | Internet data plus human ratings of answers | **Real outcomes** of actions: tests pass or fail, the user undoes or keeps, money is lost or saved |
| Knowledge of its own reliability | A self-reported confidence that is often miscalibrated | A **measured track record** per agent per task region, kept as a posterior with calibration tests |
| Memory | Context window plus optional retrieval | **Experience store** that changes beliefs, trust and thresholds |
| Model updates by the vendor | Behaviour changes silently | **Drift detection** (forgetting factor, change-point test), then re-routing |
| Role of the human | Source of prompts. Approves tool calls through fixed permission prompts | **Modelled participant** whose value is measured per scenario. Escalation follows a value-of-information rule |
| Multi-model | One vendor's model. It will not rank a rival above itself | **Vendor-neutral**. Claude is one agent among many, ranked only by outcomes |
| Unrelated A and B | Associations absorbed from co-occurrence in pretraining | Explicit bridge search (path, analogy, causal), **kept only if an outcome test confirms it** |
| Changing files and systems | Edits in place (git helps afterwards) | **Copy-on-write invariant**: the original is provably unchanged; promotion needs a test plus a human |
| Tone | One persona style | A **tone policy** learned per situation, never sounding more sure than its calibrated confidence |
| Explanation | Chain-of-thought text that is not guaranteed to be faithful | A **decision trace**: which beliefs, which numbers, which constraint bound, and what would have changed the decision |
| Values | Trained in once (constitution or human ratings), the same for everyone | A **value vector with scenario-dependent weights**, learned from people's revealed choices: a population prior plus a personal posterior |

**What NI possesses that the agentic architecture does not:**
1. **A measured track record**, per agent, per task region, updated by real outcomes.
2. **A model of the human** with measured value, so it can say why the human is needed.
3. **An explicit decision rule** that prices irreversibility, instead of per-tool permission prompts.
4. **Continual learning without retraining**, because its beliefs are sufficient statistics.
5. **Neutrality across vendors**, which no single vendor's agent can offer.
6. **Invariants**: verified bridging, copy-on-write, and hard values that are never traded.

**Pitch in one sentence:** *Agentic AIs are workers that answer. NI is the judgement that learns, from their real outcomes, which worker to trust, when, and when a human must decide.*

**Honest note for the pitch.** Frontier labs could add some of these pieces to their own agents. The defensible part is:
- the outcome data gathered across many vendors;
- the neutrality between vendors;
- mathematics that has been tested on held-out data.

NI depends on the workers. It governs them; it does not replace them.

---

## 4. The governing mathematics (one objective, nineteen layers)

Notation:
- **Agents.** AIs and bots are `a_1 ... a_K`.
- **Tasks.** A task arrives as context `x` with embedding `phi(x)`.
- **Scenario.** The scenario vector is `s` (section 5).
- **Time steps.** `t = 1, 2, ...`

### 4.1 One objective governs everything

NI's state is a set of beliefs, because it never sees the true state of the world:

```
S_t = (B_t, G_t, M_t, Z_t)
  B_t : beliefs about every agent (capability posteriors, calibration, drift)
  G_t : concept and causal graph (what relates to what, and what causes what)
  M_t : model of the human(s): value weights, expertise, availability, mood
  Z_t : scenario state, including external factors
```

An action is `a_t = (agent k, decision d, tone tau, question q)`. NI chooses a policy `pi` to solve:

```
maximise   J(pi) = E[ sum_t  gamma^t * ( w(s_t) . v(o_t)  -  C(a_t) ) ]

subject to
  P(irreversible harm at step t) <= epsilon(s_t)        chance constraint
  hash(original artifact) unchanged                     copy-on-write invariant
  hard values never traded (law, consent, safety)       lexicographic constraints
  d in D_human  =>  explicit human approval             human authority
```

- `v(o)` is the **value vector** of an outcome (section 6).
- `w(s)` are **scenario-dependent value weights** learned from people.
- `C(a)` is cost: money, latency, and the human's time.

Formally this is a **constrained partially observable Markov decision process (constrained POMDP)**. Every layer below is one of three things:
- a **belief update**: what is true;
- a **decision rule**: what to do;
- an **invariant**: what must never happen.

**Why this matters for investors:**
- A router has a lookup table.
- NI has an objective, constraints and beliefs.
- Each layer is a separately testable piece of solving that objective.

### 4.2 Layer map

| Layer | Question it answers | Core math | Algorithm | Test that proves it |
|---|---|---|---|---|
| L0 Society | Who is available? | Agents as black boxes `f_k: X -> Y` with cost and latency | Registry + adapters | - |
| L1 Experience | What happened? | `e_t = (x, s, k, y, o, h, v)` | Append-only ledger | Completeness audit |
| L2 Capability | Who is good at what? | Beta posterior with forgetting, change-point | Counting + CUSUM | Calibration error, drift caught |
| L3 Outer brain | What is the answer? | Calibrated log-loss stacking | v3/v4 (built) | Held-out accuracy |
| L4 Inner brain | Is the answer right? | `q(x) = P(correct \| decision pattern)` | Metacognitive learner (built) | AUROC(q) > AUROC(confidence) |
| L5 Decision | Act, verify, ask, stop? | Expected utility + value of information | Utility evaluator | Regret vs oracle, escalation precision |
| L6 Selection | Which agent? | Contextual bandit, Thompson sampling | Posterior sampling | Regret curve flattens |
| L7 Causality | Does X cause Y? | Structural causal model, `P(Y \| do(X))` | Causal discovery + interventions on copies | Interventional prediction accuracy |
| L8 Bridging | How are A and B related? | Max-probability path, structure mapping, novelty bonus | Graph search + analogy | Bridges that improve held-out outcomes |
| L9 Understanding | Do I know what you mean? | Intent entropy, expected free energy | Active inference | Fewer wrong inferences per question asked |
| L10 Scenario | What situation is this? | Scenario vector + change detection | Embedding + clustering | Scenario predicts outcome beyond task |
| L11 Human value | Why is a human needed here? | Heterogeneous treatment effect, VOI, Shapley | Uplift model | Escalation precision, monotonicity tests |
| L12 Values | What matters here? | Value vector, Bradley-Terry weights, hierarchical Bayes | Preference learning | Predicts held-out human choices |
| L13 Affect and tone | How should I sound? | Appraisal vector, tone policy | Contextual bandit | Fewer corrections and disengagements |
| L14 Wrapper model | How does that AI work? | Surrogate + active probing + Hoeffding bound | System identification | Surrogate agreement on held-out probes |
| L15 Copy-on-write | Did I damage anything? | `hash(F)` invariant, promotion gate | Sandbox + diff | Zero violations |
| L16 Continual learning | Did I forget? | Sufficient statistics, replay, EWC | Paired acceptance test | Old-task accuracy holds |
| L17 Audit trace | Why did I decide this? | Decision terms + counterfactuals | Trace emitter | A human can re-derive the decision |
| L18 Self-governance | Who governs NI? | NI's own parts are agents in L0 | Same rules applied to itself | No unapproved constraint change |

### 4.3 Layer details

**L0 - Society of agents.** Each agent `k` is a black box `f_k : X -> Y` with cost `c_k` and latency `l_k`. NI does not need its weights. It learns its **behaviour** (L14).

**L1 - Experience.** Every event becomes `e_t = (x_t, s_t, k_t, y_t, o_t, h_t, v_t)`:

| Symbol | Meaning |
|---|---|
| `x_t` | Context |
| `s_t` | Scenario vector |
| `k_t` | Agent used |
| `y_t` | Its output |
| `o_t` | The real outcome: measured, not self-reported |
| `h_t` | Human feedback |
| `v_t` | Value vector of the outcome |

The dataset is NI's own life.

**L2 - Capability belief.**
- For each agent and each task region `R(x)` (found by clustering `phi(x)`), keep `Beta(alpha, beta)` with forgetting `gamma`:
  `alpha <- gamma*alpha + o_t`, `beta <- gamma*beta + (1 - o_t)`.
- A CUSUM change-point test on the outcome stream flags a vendor update that degraded an agent.
- Cost is O(1) per event on CPU: learning without GPU training.

**L3 - Outer brain.** `p(y|x) = sum_k w_k(x) * T_k(p_k(y|x))`, with per-predictor temperature `T_k` and stacking weights learned by log-loss on a calibration slice. A new learner joins only if it beats all existing ones on the slice; this is the v4 rule.

**L4 - Inner brain.**
- **Definition:** `q(x) = P(correct | agreement, confidence, entropy, novelty, history)`.
- **Criterion:** `AUROC(q) > AUROC(raw confidence)` on held-out data.

**L5 - Decision.**
- Choose `d in {act, verify, ask_human, stop}` to maximise `U(d) = q*G_d - (1-q)*L_d(risk) - C_d`.
- `L_d` grows with irreversibility: delete, pay or send cost more than read.
- Asking a human follows the value-of-information rule in section 5.4.

**L6 - Selection (the anti-router).**
- Agent choice is a contextual bandit with Thompson sampling on the L2 posteriors.
- Regret against the best agent in hindsight grows like `O(sqrt(K*T*log T))`.
- A fixed "image -> Gemini" rule has no such guarantee and never adapts.

**L7 - Causality (beyond pattern matching).**
- **The question.** Pattern learners estimate `P(Y | X)`. NI must also ask `P(Y | do(X))`: would the outcome change if I changed X?
- **The model.** A structural causal model is built over logged variables using causal discovery (constraint-based PC, or continuous NOTEARS).
- **The test.** Edges are confirmed by **interventions on copies** (L15), where NI is free to experiment without risk.
- **What it enables.** Root-cause answers ("the failure is caused by the model update, not by the task") and protection against spurious correlations.

**L8 - Bridging unrelated A and B.** Concepts live in a graph, or a hypergraph when a relation joins more than two concepts.
1. **Path bridge:** `z* = argmax over paths A -> ... -> B of prod P(edge)`.
2. **Analogy bridge:**
   - If a known pair (C, D) has relation `R`, test whether `B ~ R(A)`.
   - Use structure mapping: maximise shared *relations*, not surface features.
3. **Causal bridge:** A and B share a cause or lie on a causal path in L7.
4. **Novelty bonus:**
   - `score = P(bridge) + beta * surprise(bridge)`.
   - The bonus makes unusual links get explored instead of discarded.
5. **Verification rule:**
   - A bridge is kept only if using it improves a held-out outcome.
   - Otherwise it is a hallucination and is removed.

**L9 - Understand the scenario first.**
- **Intent belief.** Keep `P(intent | context)`. Act only if `H(intent | context) < tau_H(stakes)`. The threshold falls as stakes rise.
- **Choosing a question.** Pick it by **expected free energy** from active inference, `G(question) = risk + ambiguity`.
- **What that means.** NI asks the question that most reduces ambiguity about the outcome the user cares about.
- **In plain words.** It does not jump in, and when it asks, it asks the most useful question.

**L10 - Scenario model.**
- The scenario vector `s` is defined in section 5.1.
- Scenario types are **discovered** by clustering past experience, not hard-coded.
- External change is detected with distribution-shift tests on `s`: a new regulation, a market move, a model update, or data drift.

**L11 - Human value.** Section 5.

**L12 - Values.** Section 6.

**L13 - Affect and tone.** Section 6.6.

**L14 - Wrapper model of any AI.** Section 7.

**L15 - Copy-on-write.**
- NI works on `F' = copy(F)` and applies a transform `T`.
- It promotes only if all of these hold:
  - `test(F') >= test(F)`;
  - the gain is greater than a margin;
  - a human approves.
- **Invariant:** `hash(F)` is unchanged until promotion. This is measured, not assumed.

**L16 - Continual learning without forgetting.**
- **Beliefs never forget by accident.** L2 counts and L12 weights are additive sufficient statistics, so new data cannot overwrite old knowledge except through the deliberate forgetting factor.
- **Neural parts use two safeguards:**
  - replay of stored experience;
  - Elastic Weight Consolidation (EWC), a penalty on moving weights that mattered for old tasks.
- **Every change passes a paired test** on the same held-out split, covering old tasks too, before it is accepted. This is already practised; see v4.

**L17 - Audit trace.** Every decision emits:
- the inputs;
- the beliefs used (with counts);
- each term of `U(d)`;
- which constraint was binding;
- a counterfactual of the form "I would have chosen X if factor j had been below Y".

A human can re-derive the decision from the trace. This is the deterministic-auditability requirement from the research notes, met without pretending the system is deterministic.

**L18 - Self-governance.**
- NI's own predictors are agents in L0, with their own trust posteriors.
- Hard constraints and value tests are read-only to NI. Changing them requires a human.
- If NI's own `q` becomes miscalibrated, its autonomy budget shrinks automatically.

---

## 5. The human value model: which factors, which scenarios, and how the decision changes

The earlier draft said NI measures "the human's value". This section answers the open questions:
- Which factors?
- Which scenarios?
- Does it include external conditions?
- Does it change with the scenario?
- Do the factors themselves change?
- Does the outcome change when the factors change?

### 5.1 The factors (the scenario vector `s`)

| Group | Factors measured | Where the signal comes from |
|---|---|---|
| **Task** | Stakes (money, safety, legal, reputation), reversibility, novelty (distance to past experience), ambiguity (intent entropy), domain, required expertise, time to undo | Task description, action type, L9, L1 history |
| **Agents** | Posterior reliability in this region, disagreement between agents, calibration error, recent drift, cost | L2, L3, L4 |
| **Human** | Measured accuracy in this region, expertise, authority and role, availability, current load (decisions asked today), response latency, preference for being consulted, current mood | Ledger of past human decisions, explicit settings, L13 signals |
| **External** | Deadline and time pressure, environment (test or production), jurisdiction and regulation, third parties affected, information freshness (did the world change: news, prices, model releases), system load and budget, time of day | Clock, environment metadata, change detectors, policy files |
| **Values** | Which hard values are touched (consent, privacy, legality, safety); which soft values trade off | L12 |

### 5.2 Scenarios are not a fixed list

- A scenario is the vector `s`.
- Scenario types are discovered by clustering the experience store, for example:
  - "irreversible payment under deadline";
  - "creative task with no right answer";
  - "routine low-stakes edit".
- New types appear when new clusters form.

**Factor discovery.**
- If NI's prediction errors correlate with a logged variable that is not yet a factor, NI proposes it as a new factor.
- It is adopted only if a paired test shows better predictions.
- So the factor list itself grows from evidence.

### 5.3 The human's contribution is a function of the scenario

```
Delta_h(s) = E[ outcome | human involved, s ]  -  E[ outcome | no human, s ]
```

This is a **heterogeneous treatment effect**: the human's value differs by scenario.
- **How it is estimated.** Uplift models such as causal forests, with doubly robust estimators, on logs where human involvement varied.
- **Getting that data safely: shadow mode.**
  - NI records what it *would* have done.
  - The human decides as usual.
  - Comparing the two gives paired data with no risk.

The human's value is a **vector**, not one number:

```
V_h(s) = ( accuracy uplift Delta_h(s),
           harm avoided,
           authority required (0/1, from law, policy or the user's own rule),
           preference information (taste only this human knows),
           teaching value (information gain to NI's beliefs from the human's answer),
           accountability (someone must own the decision) )
```

### 5.4 When to ask: the value-of-information rule

```
VOI(s) = E_answer[ max_d U(d | answer, s) ]  -  max_d U(d | s)

ask the human  if  VOI(s) > c_h(s)   or   authority_required(s) = 1
```

`c_h(s)` is the cost of the human's time:
- it rises with their current load;
- it falls with stakes.

NI therefore asks more when it matters and less when the human is busy with something trivial. It always asks when authority is required.

### 5.5 Telling the human why they are needed

The reasons come from a Shapley attribution of `VOI(s)` over the factors. Example message:

> "I need you here. The main reasons are:
> - the payment cannot be undone (+41% of the reason);
> - the two agents disagree on the amount (+27%);
> - you have been right on 9 of 10 contracts like this (+18%)."

That is how NI tells humans why they are important without flattering itself or them.

### 5.6 Does the decision change when the factors change? (tests)

1. **Monotonicity (hard properties).** These are enforced with monotone models and checked by property tests:
   - higher irreversibility, stakes or disagreement never *lowers* the chance of escalation;
   - higher agent reliability never *raises* it.
2. **Counterfactual pairs.** A test suite of scenario pairs that differ in exactly one factor, each with a known expected direction. The pass rate is reported.
3. **Sensitivity report.** For each decision, `dDecision/ds_j`, or the smallest change in factor `j` that would flip the decision, goes into the L17 trace.
4. **Drift report.** Factor effects are re-estimated over rolling windows. NI reports when a factor's effect changed, for example "deadlines now matter more for you than in March".

### 5.7 Why this is not a robot brain

- Thresholds `tau(s)` are learned per scenario and per person.
- **Hierarchical Bayes:**
  - a new person's parameters start at the population prior;
  - they move to their own posterior as evidence accumulates;
  - `theta_person ~ N(theta_population(s), Sigma)`.
- The same request gets a different decision for a different person in a different situation. The reason is always visible.

---

## 6. Values and affect: what NI considers, since it cannot feel

NI cannot feel. It can **see**. It sees the patterns people make, both this user and people in general, and turns them into values.

### 6.1 What it can see

- **Actions:** choices, approvals, rejections, corrections and edits.
- **Regret:** undo actions and later reversals, which mark delayed regret.
- **Time:** the time people spend, and the time they wait before replying.
- **Language:** words of frustration or relief, short replies, repeated requests.
- **Reach and ownership:** who else was affected, what people paid for, and what they kept.
- **Public patterns of behaviour:**
  - preference datasets;
  - reviews;
  - laws, policies and professional codes;
  - norms written in documentation.

### 6.2 The value vector `v(o)`

| Value | How it is measured |
|---|---|
| Safety / harm avoided | Harm events, near misses, severity scale |
| Truth / honesty | Verified correctness, hallucinations caught |
| Human autonomy and consent | Actions taken without required approval (must be zero) |
| Privacy | Personal data exposed or sent outside (must be zero) |
| Legality and compliance | Policy checks passed |
| Reversibility | Time and cost to undo |
| Quality | Tests, reviews, user keeping the result |
| Cost | Money and compute spent |
| Speed | Latency to outcome |
| Fairness and third parties | Effects on people not present |
| Relationship / wellbeing | User frustration signals, disengagement, trust over time |
| Growth | Does the human learn and need less help on this task later |

### 6.3 Hard values and soft values

- **Hard values** are constraints and are never traded. They form a lexicographic order: no gain in speed or cost can buy a breach. Examples:
  - consent;
  - privacy;
  - legality;
  - irreversible harm above `epsilon`.
- **Soft values** trade off through weights `w(s)`.

### 6.4 Learning the weights from what people do

From pairwise choices (Bradley-Terry, a form of inverse reinforcement learning):

```
P(human prefers A over B | s) = sigmoid( w(s) . (v(A) - v(B)) )
```

- **Everybody's patterns are the prior:** `w_population(s)`, learned from public preference data and norms.
- **Your patterns are the posterior:** `w_you ~ N(w_population(s), Sigma)`, updated with each observed choice.
- **Test:** NI must predict held-out human choices better than the population prior alone.

### 6.5 Conflicts and uncertainty

- **Hard values in conflict:** stop and ask.
- **Soft values in conflict, weights uncertain** (high posterior variance): present the Pareto options with their trade-offs instead of choosing silently.
- **Moral uncertainty:** keep several value hypotheses and prefer actions that are good under all of them. This is maximin, or maximising expected choice-worthiness.

### 6.6 Affect and tone without feelings (appraisal theory)

**1. Appraisal of the situation (OCC and Scherer appraisal theory):**

```
alpha(s) = ( goal relevance, goal congruence, agency (who caused it),
             controllability, urgency, novelty, norm compatibility )
```

**2. Estimate the user's state.**
- The user's mood `m` is estimated from the signals in 6.1.
- It is a reading of the situation, not a feeling of its own.

**3. Choose the tone.**
- The tone policy is `pi(tone | alpha, m, history)`, over calm, warm, firm, playful, confident and assertive.
- It is learned as a contextual bandit.
- Its reward is the user continuing without correcting or disengaging.

**4. Honesty rule.** The confidence of the tone can never exceed the calibrated confidence: `assertiveness <= f(q(x))`. Arrogance is allowed only when the evidence is strong, and never as a bluff.

Examples:

| Situation | Tone |
|---|---|
| High urgency, low controllability | Calm and firm |
| Low stakes, playful user | Playful |
| User about to make an irreversible mistake with high `q` | Assertive |

### 6.7 More ideas in the same direction

- **Value-drift alarm:** if a user's revealed weights shift sharply, NI notices and asks whether their priorities changed.
- **Third-party weight:** people affected but not present get an explicit weight (externalities), so "the user wanted it" is not the only test.
- **Regret as delayed outcome:** decisions that are undone or complained about later count as negative outcomes and retroactively update beliefs.
- **Domain priors:** values weigh differently in medicine, finance, games and art. Domain is part of `s`.
- **Values as tests:** each hard value owns a scenario test suite that must pass before any NI update ships (L16, L18).
- **Bias audit:** values learned from people inherit their biases. NI reports when a learned weight disadvantages a group, and a human decides.

---

## 7. The gluey wrapper: learning any AI's "brain" from its behaviour

### 7.1 Attach protocol (self-governing)

`Attach -> Observe -> Map -> Model -> Copy -> Transform -> Verify -> Propose -> Promote (human only)`

### 7.2 Three depths, chosen automatically

| Access | What NI reads | What it builds |
|---|---|---|
| **White box** (open source) | Code, configs, model graph (layer types and sizes), weights, activations | Structural map plus behavioural map. It can probe internal features |
| **Grey box** (API with log-probabilities or tool traces) | Output probabilities, tool calls, timings | Calibration and decision-path map |
| **Black box** (closed model or app) | Inputs and outputs only | Behavioural map only: the "brain from the answers" |

### 7.3 Behavioural fingerprint `Phi_k`

For each agent NI learns:
- **Capability map:** `r_k(x)` by task region, from L2.
- **Failure map:** where and how it fails.
- **Calibration curve:** stated confidence against real accuracy.
- **Consistency:** does it give the same answer to paraphrases?
- **Boundaries:** refusals and limits.
- **Style and tool-use habits.**
- **Cost and latency.**
- **Drift over time.**

This is the "pattern and knowledge of the brain based on its answers".

### 7.4 Surrogate model and active probing

```
f_hat_k = argmin_f  E_x[ loss( f(x), f_k(x) ) ]           surrogate of agent k
x*      = argmax_x  information_gain( failure map | x )   next probe
```

NI chooses the probes that teach it the most about where the agent fails, instead of probing at random.

### 7.5 How many probes before trusting a claim

By Hoeffding's inequality, estimating an agent's success rate in a region within `epsilon` with confidence `1 - delta` needs:

```
n >= ln(2/delta) / (2 * epsilon^2)
example: epsilon = 0.05, delta = 0.05  ->  n >= 738 probes per task region
```

This gives NI a principled answer to the question "how sure are you about this agent?".

### 7.6 What it can and cannot recover

- **Can:** the agent's function on the distribution that was probed. That is enough to govern it.
- **Cannot:** weights, training data, or behaviour far outside the probes.
- **Legal limit:** many providers' terms forbid using outputs to train a competing model. Fingerprinting for governance is different from distilling a clone. Check each provider's terms.

### 7.7 What the wrapper does on the copy

Example transforms:
- cache repeated calls;
- compress prompts;
- swap an expensive agent for a cheaper one where the fingerprints are equal;
- reorder or parallelise a workflow;
- add verification steps.

Each transform passes the L15 gate. `hash(original)` is unchanged, and this is measured.

### 7.8 Self-application

NI applies the wrapper to itself. Its own components get fingerprints, and its own speed-ups go through the same gate (L18).

---

## 8. Research notes and what they mean for NI

These notes come from my own research, pasted into this chat. They were **not re-verified in this session**; check names, funding figures and dates before using them in a pitch.

### 8.1 What Y Combinator says it wants (per my notes)

- **No explicit "Natural Intelligence" request.** The Requests for Startups (RFS) do not ask for it.
- **Current emphasis:**
  - AI for physical systems and robotics;
  - zero-shot vertical models (biology, energy, manufacturing);
  - infrastructure;
  - reinforcement-learning environments.
  The notes cite Reific, which learns reasoning over time-series sensor data.
- **The RFS is not a checklist.** YC funds companies outside the list when there is customer evidence.

### 8.2 Fields that move beyond pattern matching (per my notes)

- **Causal AI:** cause and effect instead of correlation. Examples given: the bioAI project at Simula (causal representation plus continual learning), and Causaly (knowledge graphs plus reasoning).
- **Hypothesis generation across unrelated fields:** reasoning agents that link scattered findings, such as neuronal function and cholesterol metabolism, into testable hypotheses.
- **Biological computing:** living neurons on electrode arrays (The Biological Computing Company).
- **Abstract reasoning benchmarks:** Chollet's ARC tests rule-finding from a few examples instead of memorised patterns.
- **The usual names for what I call NI:** Causal AI, neuro-symbolic AI, world models and active inference.

### 8.3 Why the market could be large (per my notes)

- Regulated industries cannot deploy systems that guess: healthcare, aviation, energy, defence, banking.
- A verifiable, auditable system unlocks those budgets.
- Learning structurally rather than by brute force could cut compute cost sharply.

### 8.4 The four bottlenecks from my notes, mapped to NI

| Bottleneck | What investors need | NI's answer | Where | Status |
|---|---|---|---|---|
| 1. Mathematical formalism | Math, not buzzwords | Constrained POMDP objective plus 19 layers, each with math and a test | Section 4 | Drafted; L2-L4 built |
| 2. Continual learning loop | Learns live from single events without forgetting | Sufficient-statistic beliefs, replay, EWC, paired acceptance | L2, L16 | Belief updates built; paired tests practised |
| 3. Deterministic auditability | Know *why* it decided | Decision trace with terms, constraints and counterfactuals | L17 | Proposed |
| 4. A wedge use case | One domain where pattern matching fails, with a benchmark | See 8.6 | 8.6 | To choose |

### 8.5 Two corrections to keep the pitch honest

- **"Deterministic" is the wrong word for NI.** NI is probabilistic underneath, like every learning system.
  - The honest and stronger claim is: **calibrated, auditable, and bounded-risk, with hard constraints that never bend.**
  - Regulated industries already accept probabilistic models (for example credit scoring under banking model-risk rules) when they are validated, documented and monitored. That is exactly what L4, L16 and L17 provide.
- **Market-size statements** such as "multi-hundred-billion" are speculation. Investors will ask for a bottom-up market size for the wedge.

### 8.6 Wedge candidates

| Wedge | Why pattern matching fails there | Benchmark that would prove NI | Fit with what is built |
|---|---|---|---|
| **A. Governance for teams running several AI coding and ops agents** | Agents are confidently wrong; vendor updates silently change behaviour | Predict test or merge success before acting (AUROC vs the agent's own confidence); escalation precision; regret curve vs a fixed router | **Highest.** Trust gate, ledger and outer/inner brains exist. Public-data AUROC is 0.52 today, so richer features are needed |
| B. Root-cause analysis in operations or manufacturing | Correlated alarms hide the true cause | Top-k root-cause accuracy on incident datasets vs an LLM baseline | Needs L7 and L8 built |
| C. Fraud and risk review with humans in the loop | Rare events, costly mistakes, human authority required | Cost-weighted loss under a fixed human-review budget | Needs L11 and L12 built |

**Recommendation: wedge A.** It matches the code and data that already exist, and its outcomes are cheap to verify: tests pass or fail.

---

## 9. What is already built and measured (November 2026)

Code: `D:\new_automation\natural_intelligence\` (Python, local, free; RTX 3050 6 GB; CPU-heavy by design).

| Layer | Built | Measured result |
|---|---|---|
| L3 outer brain | Four voting predictors (Logic, Pattern, Verifier, Exploratory), a calibration slice (v3), and a tree learner that joins only when it beats all four (v4) | **85.5%** mean held-out accuracy on 41 datasets (text, image, audio, video, graph). 83.6% on all 46, including new hard sets |
| L3 features | Frozen encoders per modality; stronger encoders (enc2) | +17 to +61 points over hand-built features. The stronger text encoder adds +8 to +10 points on sentiment sets |
| L16 paired acceptance | Paired A/B before adopting any change | v4 tree learner: +3.1 (twitch_egos), +3.5 (imdb_binary). Identical to v3 where trees do not help |
| L4 inner brain | Learns "was the outer right", plus verification by perturbation | Beats raw confidence on text (AUC 0.88 vs 0.82) and image (0.84 vs 0.81). Ties audio and video. **Loses on graphs** |
| L5/L6 trust gate | HTTP service: POST /trust before an action, POST /outcome after | On 143 real manager outcomes: AUROC 0.78 vs a 0.68 baseline. On 3,937 public agent runs: **0.52, which is chance**. No proceed threshold reached yet |
| L1 experience | Outcome ledger plus public agent trajectories | Too few real outcomes so far (143) |
| Execution (bots) | Desktop and app automation organs; front door `hojaiga.bat` | Built. **NI not yet tested live on other apps** |
| L1 experience (governor) | `gov_ledger.py`: hash-chained append-only ledger of NI's own decisions and outcomes, failure reason kept | Tamper test: an edited past outcome is caught at its line. Live: decisions are joined to outcomes as they arrive |
| L2 capability | `gov_beliefs.py`: Beta counts with forgetting per agent x region (hierarchical prior), Bernoulli CUSUM drift | Held-out (newest 25%, online): AUROC 0.745 vs 0.729 for a frozen per-kind rate; the log-loss gain CI spans 0 (-0.001 to +0.007). Injected 3% -> 30% drift caught in 34 events, no false alarm. 3 real alarms, 2 of 3 followed by a higher failure rate |
| L5 decision + L11 VOI + autonomy | `gov_decide.py`, `gov_core.py`: expected utility over {proceed, verify, ask, stop}, VOI with a modelled human, earned levels from the LCB (brief 2, 3.4), lexicographic hard values | Same 2,236 held-out actions: 2.1 human asks per 100, all in authority classes; escalation precision (failed or authority) **0.346 vs 0.210** for a same-budget risk threshold; failure recall **0.377 vs 0.403** (tie, CI -0.13 to +0.08). It does not catch more failures than the plain gate |
| L6 selection | `gov_select.py`: Thompson sampling + CUSUM reset | **Simulated only**: regret 88 vs 431 (no forgetting) and 750 (fixed router) after a vendor update. No real test possible: the human picks the model |
| L15 copy-on-write | `gov_cow.py`: copy, transform, test both, hash the original at every step, human-only promotion | Tests: correct transform eligible, breaking one refused, one that touches the original caught; zero violations on the legitimate runs |
| L17 trace | Every verdict carries factors, utility terms, VOI, binding constraint, exact Shapley reasons, nearest flip per factor | Verdict and every counterfactual re-derive from the trace alone (500 random scenarios, 0 mismatches) |
| L18 self-governance | `gov_policy.py` lock (human-only approve), `gov_self.py` | Gate's raw scores were miscalibrated (ECE 0.131 at a 3.4% base rate); isotonic map adopted after it beat raw log-loss on a later slice (0.225 -> 0.122); autonomy budget 0.80. A tampered policy makes the governor ask the human for everything |
| Branch engine (keep every child alive) | `gov_branch.py`: all branches on copies in parallel, Pareto + P_best under uncertain weights, information-gain question when tied | 7 synthetic tests pass. **One real task** (`BRANCH_RUN1.md`): 6 branches from 5 vendor routes against a hidden 18-check test. First branch (Claude Code) produced nothing (authentication failure). Most confident and NI both picked an 18/18 branch. NI rejected a 14/18 branch with reasons, and did not ask about sub-noise differences. One task is a demonstration, not evidence |
| Properties (5.6) | `gov_tests.py` | 36/36: monotonicity on 4,000 random scenarios per factor, 11 counterfactual pairs, VOI >= 0, Shapley efficiency, tone honesty cap |
| L7-L10, L12-L14, L16 (beyond v4 paired tests) | Not built as NI layers yet | - |

---

## 10. My list of components to build

(Paste my list here, then map each item to a layer in section 4.)

- ...
- ...

---

## 11. Honest limits (keep these in every answer)

- **Closed models expose no weights.** Claude, GPT and Gemini only reveal behaviour. NI governs closed AIs from behaviour (section 7), and white-box understanding of open models is a research field in itself (for example Goodfire).
- **No-GPU learning has a limit.** It works for beliefs, memory, rules and small models. It does not make NI out-reason a frontier model. NI's edge is judgement, combination and verification, not raw reasoning.
- **Far analogy is unsolved** in 2026 research. Every bridge must be verified by outcomes, or it is a hallucination.
- **Emotions are not felt.** They are appraisal plus tone policy: NI reads affect in the situation; it does not feel it.
- **Measuring human value needs varied data.** It needs logs where humans were and were not involved, from shadow mode or randomised review. Without them, `Delta_h` is biased.
- **Learned values inherit human biases.** A bias audit and human sign-off are required.
- **Fingerprinting is bounded by the probes.** Behaviour far from the probed distribution is unknown. Provider terms may forbid training clones on outputs.
- **NI is not deterministic.** It is calibrated, auditable and constrained. Never pitch it as deterministic.
- **The governor claim is not proven yet.** It needs hundreds of real outcome logs from live use. Until then, the claim rests on the architecture plus the measured outer-brain and inner-brain results.
- **Name clash.** "Natural Intelligence" is already a funded AI company (nisys.ai, Boise, oscillatory and neuromorphic AI). Keep the concept, and pick a distinct product name.

---

## 12. Closest existing work (so we do not reinvent it)

- **Model routers** (OpenRouter, Martian, Not Diamond, RouteLLM). They pick a model per request, but do not learn from your own outcomes.
- **AWS "graduated autonomy".** Agents earn and lose permissions from scored outcomes. It is the closest shipped idea, but it is configured by rules.
- **LeCun / Dupoux / Malik "System M"** (March 2026). A meta-control layer, published as a proposal only.
- **Other related systems:**
  - AMI Labs (world models, $1.03B);
  - Ndea (Chollet, program synthesis);
  - VERSES (active inference);
  - Google Nested Learning / HOPE (continual learning);
  - Sakana Darwin Godel Machine (self-improving code);
  - OpenCog Hyperon (cognitive architecture);
  - AIOS, Letta and Mem0 (agent operating systems and memory).
- **From my research notes:**
  - Causaly (causal knowledge graphs);
  - Simula bioAI (causal plus continual learning);
  - The Biological Computing Company;
  - the ARC benchmark.
- **Methods NI borrows. NI's contribution is the combination, not these parts:**
  - structural causal models;
  - uplift modelling and causal forests;
  - value of information;
  - Shapley attribution;
  - Bradley-Terry preference learning;
  - appraisal theory;
  - active inference;
  - Thompson sampling;
  - EWC;
  - the Hoeffding bound.
- **The gap.** None of these ships the composite: one learned judgement layer above many different AIs and bots that learns from their real outcomes and measures why humans are needed.

---

## 13. What would convince an investor (proof plan)

1. **Trust beats confidence.** NI's `q` predicts real agent success better than the agent's own confidence (AUROC on held-out live runs).
2. **NI beats the best single agent.** NI's combination or selection is more accurate than the best individual agent on the same tasks, at equal or lower cost.
3. **The regret curve flattens** for NI over time (L6). A fixed router's does not.
4. **Human value is measured.** Escalations have high precision: when NI asks a human, the human was actually needed. `Delta_h(s)` is estimated per scenario.
5. **Factors move decisions correctly.** Monotonicity and counterfactual-pair tests pass (section 5.6).
6. **Values predict people.** Learned value weights predict held-out human choices better than the population prior (section 6.4).
7. **Fingerprints are accurate.** Surrogate agreement with each agent on held-out probes meets the Hoeffding-sized targets (section 7.5).
8. **Zero damage.** The copy-on-write invariant holds across every wrapper run (L15).
9. **No forgetting.** Accuracy on old tasks holds after each accepted change (L16).
