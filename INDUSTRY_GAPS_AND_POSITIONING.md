# Industry Gaps, What YC Is Asking For, and Where Hojaiga Fits

Research date: 4 Nov 2026. Most sources below are secondary write-ups or vendor blogs; YC's own site could
not be fetched from the build sandbox, so verify YC wording on ycombinator.com/rfs before quoting it in a pitch.

## 1. The term for what we are building

The industry name closest to the Hojaiga brain is **neurosymbolic AI**: a neural network for perception and
language, combined with symbolic structure (knowledge graphs, rules, solvers) for exact reasoning and
verification. Write-ups describe the same split we use: the neural part handles language and intent; a
symbolic layer verifies and executes, and can catch contradictions the neural part produces.
Related terms: *cognitive architecture*, *continual learning*, *company brain*.

Our angle: neurosymbolic **plus** continual learning from feedback **plus** visual teaching output.

## 2. Gaps the industry reports

| Gap | What sources say | How the Hojaiga brain answers it | Where in code |
|---|---|---|---|
| Pilots don't reach production | MIT NANDA *GenAI Divide* (2025): only ~5% of pilots reach production (methodology is narrower than the headline). A March 2026 survey of 650 tech leaders: 78% have pilots, 14% reached production scale. Gartner, Apr 2026: 28% of AI use cases fully meet ROI | Learns the customer's own material on site (`brain ingest`, `brain train`), no outside model required, so there's no integration project before value | `HojaigaBrain.ingest`, `CortexTrainer` |
| Traceability / explainability | Dataiku/Harris (600 CIOs): 85% saw traceability gaps delay or stop AI projects | Every answer keeps a per-layer thought trace, sources, and a confidence breakdown (`brain ask --trace`) | `Thought.trace`, `VerifyLayer` |
| Hallucination / unreliable output | Neurosymbolic vendors argue pure LLMs are probabilistic and need symbolic checks; one 2026 paper links fine-tuning hallucinations to forgetting | Answers must be grounded in evidence; contradiction check; exact calculator for math; calibrated confidence; "I don't know yet" instead of guessing | `VerifyLayer`, `safe_calculate` |
| Models forget / can't learn continuously | Catastrophic forgetting is named a primary barrier to continual learning (2026 preprints) | Replay buffer mixed into every training run; symbolic memory never forgets; failure memory | `CortexTrainer._replay_*`, `failure` table |
| Repeating the same mistakes | (general complaint) | A refuted answer is stored and demoted forever; human corrections are recalled even for paraphrases | `HojaigaBrain.feedback`, `ThinkLayer` |
| Ownership / governance / privacy | Integration, security and privacy are top barriers (~26% each in one survey) | Runs locally; PII and secrets are redacted at the first layer; teachers are opt-in | `FilterLayer`, `organ_37` teacher manager |
| Cost of external APIs | (implied by ROI findings) | Self-reliance grows: confirmed answers are served natively; teachers are used only when unsure | `organ_08` cortex, `ni stats` |

## 3. What YC is asking for (2026 Requests for Startups)

- **Company Brain (Summer 2026)**: an AI system that is the institutional memory of a company. It continuously
  ingests documents, email, chat, meetings, code and customer conversations, structures that knowledge, keeps it
  current, and turns it into skills agents can execute.
  → *Hojaiga fit:* `brain ingest` + concept graph + relation triples + failure/feedback memory is exactly this
  memory layer, and the desktop automation organs are the "execute" half.
- **The Primer (Fall 2026)**: an adaptive tutor that teaches young children reading, writing and arithmetic at the
  quality of a devoted private tutor and at consumer scale. Write-ups suggest per-child learner profiles,
  real-time difficulty, and a parent dashboard.
  → *Hojaiga fit:* the animated lesson renderer (textbook/storybook → narrated animated scenes, grade-aware) plus
  the existing tutor organs and learner profile.
- **Spring 2026**: AI-native agencies / services that deliver outcomes rather than software.
- **Fall 2026 themes**: AI in the physical world, agents that run whole workflows.

Pitch suggestion: lead with **one** of these (Company Brain for B2B, or The Primer for consumer education), and
show the other as the same brain applied to a second market.

## 4. Competitors and neighbours

| Product | What it does | Our difference |
|---|---|---|
| Clicky (open source, Mac; separate Windows project) | AI buddy next to the cursor; sees the screen, talks, points, draws arrows/annotations | We build a brain that learns and grows locally, not a wrapper around one external model; lessons become animated scenes, 3D and hologram views |
| VideoTutor ($11M seed), VyraVid, nFactorial, SketchMind, Tewtor | AI explainer videos and whiteboard lessons | Ours works from *your* textbook/storybook page by page, runs offline, and its knowledge improves with feedback |
| Company-brain startups (e.g. HeyBrain, Hyper, GBrain in write-ups) | Enterprise knowledge layers | Ours adds verification, exact reasoning and failure memory, plus desktop execution |

## 5. Honest limits to state to investors

- The from-scratch neural cortex only knows what it is trained on. General world knowledge needs either a large
  dataset and GPU time, or distillation from a teacher model (supported: `brain overnight --teacher`).
- The symbolic layers are strongest on factual, procedural and quantitative questions found in the fed material.
  Open-ended creative writing still benefits from a teacher model.
- The "beats Jarvis/Ultron" framing will not survive diligence; measurable claims will: answer accuracy on a
  held-out set, % of answers needing no external API (self-reliance), errors not repeated after correction.

## Sources
- [YC Summer 2026 RFS overview (The VC Corner)](https://www.thevccorner.com/p/yc-summer-2026-requests-for-startups-ideas)
- [YC RFS Fall 2026 explained (startupideasdb)](https://startupideasdb.com/blog/yc-requests-for-startups-fall-2026)
- [The Primer – YC RFS Fall 2026 (modelence)](https://modelence.com/yc-rfs-fall-2026/the-primer)
- [Company Brain – YC RFS Summer 2026 (modelence)](https://modelence.com/yc-rfs-summer-2026/company-brain)
- [Company Brain: why YC bet on it (HeyBrain)](https://heybrain.io/blog/yc-company-brain-bet)
- [YC 2026 RFS (Tech Startups)](https://techstartups.com/2026/02/04/y-combinator-is-out-with-its-2026-request-for-startups/)
- [2026 Enterprise AI adoption gap by the numbers (First Line Software)](https://firstlinesoftware.com/blog/the-2026-enterprise-ai-adoption-gap-by-the-numbers/)
- [Enterprise AI adoption 2026 (Prem AI)](https://www.premai.io/blog/enterprise-ai-adoption/)
- [Why AI pilots fail to scale (AI Assembly Lines)](https://aiassemblylines.com/post/why-ai-pilots-fail-to-scale)
- [Why enterprise AI fails: neuro-symbolic architecture (Level Up Coding)](https://levelup.gitconnected.com/why-enterprise-ai-fails-the-hidden-trap-of-pure-probabilistic-llms-and-the-rise-of-neuro-symbolic-304dd7ad305d)
- [The neurosymbolic imperative for enterprise AI (o9)](https://o9solutions.com/articles/the-neurosymbolic-imperative-for-enterprise-ai)
- [FAOS neurosymbolic architecture (gentic.news)](https://www.gentic.news/article/faos-neurosymbolic-architecture)
- [Mechanistic analysis of catastrophic forgetting (arXiv 2601.18699)](https://arxiv.org/abs/2601.18699v1)
- [Clicky (GitHub, farzaa)](https://github.com/farzaa/clicky) · [Clicky Windows](https://github.com/Bitshank-2338/clicky-windows)
- [VideoTutor seed round (Pulse 2.0)](https://pulse2.com/videotutor-11-million-seed-backed-ai-tutoring-platform-surpasses-50-million-tiktok-views/)
