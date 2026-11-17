# NI research brief (paste word for word into Google / Gemini / Perplexity)

I am building a system I call a "Natural Intelligence governor". Please research it deeply and help me improve it.

WHAT IT IS
It is a decision layer that sits above several AI coding agents (LLM agents such as DeepSeek, GLM, MiMo, Nemotron, Claude). It does not train any neural network and needs no GPU. Its job is to direct the agents like a careful lead engineer directs a team.

HOW IT WORKS
1. A task arrives as a written spec plus an empty code file.
2. Branching: the same task is given to several agents at once. Each agent works on its own isolated copy (copy-on-write), so no attempt can damage the original or another attempt. All branches are kept, not just one.
3. Proof: every result is scored by hidden tests the agents never see. The agent's self-reported confidence is recorded but not trusted.
4. Governing: the governor combines (a) Bayesian trust beliefs per agent (Beta distributions with forgetting and CUSUM drift detection), (b) expected-utility and value-of-information reasoning about the cost of a wrong pick, (c) Thompson sampling to choose which agents to use, and (d) a set of hard values that a human approved and that are locked with a SHA-256 checksum.
5. Verdict: it either recommends the proven best branch, says two branches are equivalent, cross-questions the human when the evidence is unclear and a wrong pick would be costly, or reports that no branch passed. A human must approve before anything is promoted into the real project.
6. Learning: every outcome is written to a hash-chained ledger and updates the trust beliefs, so the system improves from outcomes without retraining a model.

CURRENT RESULT
On 7 small coding tasks with 4 free agents, the governor shipped 7/7 correct with 0 broken, while "trust the most confident agent" shipped 5/7 correct and 2 broken. Agents stated 90-96% confidence on answers that failed. This is too few tasks to be significant; I am running 20.

PLEASE RESEARCH AND REPORT ON:
A. Existing research closest to this: best-of-N sampling with verifiers, LLM ensembles and routers (e.g. RouteLLM, FrugalGPT, Mixture-of-Agents), multi-agent debate, self-consistency, test-time compute scaling, AlphaCode-style sample-and-filter, SWE-bench agent ensembles, LLM-as-judge versus execution-based verification, calibration of LLM confidence, selective prediction and abstention ("learning to defer" to humans), contextual bandits for model selection, and scalable oversight / AI control research. For each, name the key papers (authors, year, link) and how they differ from my design.
B. Existing products and companies doing agent orchestration, model routing, or AI code review/verification (for example Martian, Not Diamond, OpenRouter, LangGraph, CrewAI, AutoGen, OpenHands, Devin, Cursor, Factory, CodeRabbit, Qodo). What do they do, what do they charge, and where is the gap my governor could fill?
C. Market need: how big is the market for AI coding agents and for AI governance/assurance; what do companies say their biggest problems with AI agents are (wrong code shipped with confidence, cost, lack of audit trail, compliance such as the EU AI Act and NIST AI RMF); who would pay for "proof before ship" and a decision ledger.
D. How to make my system better than the state of the art: better verifiers when hidden tests do not exist (property-based tests, mutation testing, differential testing between branches, formal checks), how to decide when to ask the human with the fewest questions, how to merge the best parts of several branches, how to cut cost (send only hard tasks to many agents), how to detect agents peeking at tests or gaming checks, and how to prove the improvement with proper statistics.
E. Honest weaknesses: where this approach is known to fail, what critics say, and what benchmark I should use to prove it to others (SWE-bench Verified, LiveCodeBench, HumanEval+, or something else).

Please give sources with links for every claim, separate proven results from opinions, and end with a ranked list of the 10 most useful improvements I should build next.
