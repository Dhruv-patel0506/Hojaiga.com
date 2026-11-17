# Closing Hojaiga: exit checklist

Goal: publish an honest, runnable research release, then stop. "Done" means documented, safe to share and runnable with an API key. It does not mean every feature works.

## 1. Security first (before anything goes public)
- [ ] Revoke the GitHub personal access token that appears in 3 old commits (`API_KEY_INTEGRATION_COMPLETE.md`, an older `secure_key_storage.py`): GitHub > Settings > Developer settings > Tokens.
- [ ] Rotate every key in `.env` (Groq x3, NVIDIA x2, OpenRouter x2, HOJAIGA_IMAGE_KEY) and the Telegram / Discord / GitHub tokens stored encrypted in `config/secure_keys.json`.
- [ ] Do NOT make the current repository public: its history keeps the old token even after a file is deleted.

## 2. Make a clean public repository (fresh history)
Include:
- `All codes/core_organs/` (code + `si_tests_*` test suites), `claude_skills/`, `hojaiga.bat`
- selected reports: `reports/MORNING_NOV02.md`, `reports/CP2_AUDIT.md`, `reports/FIXES_OCT28_DAY.md`, this folder
- `README.md` (from `README_PUBLIC.md` here), `.env.example`, a `LICENSE` (MIT suggested)

Exclude:
- `.env`, `config/secure_keys.json`, `data/` (scans, browser profile, run logs, app databases), `models/`, `hojaiga_env/`, `venv/`, `natural_intelligence/data_user/`, `tools/`, `data/inbox/`
- `clicky/`: link to Farza's repository instead of copying it (it is MIT, but it is his project)
- anything with personal names, recent-file lists or screenshots of your own desktop

Then search the export once for `ghp_`, `gsk_`, `nvapi-`, `sk-or-`, `AIza`, `sk-ant-` before the first push.

## 3. Make it runnable with an API key
- [ ] `.env.example` (in this folder): the user adds their own key (`HOJAIGA_CLAUDE_KEY`, or free `GEMINI_API_KEY` / `GROQ_API_KEY`).
- [ ] The teacher-and-brain loop is already built (`mind/brain.py`, `organ_37_llm_gateway.py`): the hosted model decides a step, the local brain checks it, the result is proven, and proven steps are kept. Test AR86: 16/16.
- [ ] README states plainly what works and what does not (sections 5 and 6 of the report).

## 4. Show it once
- [ ] A 60 to 90 second screen recording of three things that work: the annotated scan, an Office task proven from the saved file, a Blender object built from one sentence.

## 5. Close it
- [ ] Tag `v0.1-research-release`, mark the GitHub repository "Archived", pin an issue "Open problems" (copy section 6 of the report).
- [ ] Stop local services so the laptop is yours again: Ollama, llama-server (:8081), any `ni_sched` daemon (`python ni_sched.py --stop-all`), scheduled task "HojaigaNightCheck" if it still exists.
- [ ] Post on LinkedIn (`linkedin_post.txt`), add the resume entry (`resume_entry.txt`), link the report.
