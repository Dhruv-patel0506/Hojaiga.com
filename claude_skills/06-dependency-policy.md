---
name: hojaiga-dependency-policy
description: Dependency and model policy - everything free, local, no paid APIs; known-good version pins (transformers 4.51.3, torch CPU wheels, lazy easyocr); the 5-question pre-install gate; model weights stay out of git and are downloaded locally.
---

# Skill 06 — Dependency & Model Policy (FREE / LOCAL / NO-API)

This is the project's cost law. Every dependency and every model must be free and run
locally. No SaaS, no API key, no account, no per-seat licence, no phone-home.

## The four rules
1. **Free & open only.** Accept OSI-licensed wheels (MIT/Apache/BSD). Reject anything
   needing a paid key or that uploads your data.
2. **Local runtime.** All inference happens on this machine (CPU is fine). After a one-time
   model download to the local HF cache, the system must run **offline**.
3. **Pin to what WORKS on Python 3.13.14**, not to "latest". Version drift has broken the
   build repeatedly (see below). When a requirement fails because a version is too high or
   too low, move it to the level that works and reinstall.
4. **Lazy/optional imports** for heavy engines so a missing lib degrades gracefully
   (tier self-reports `skipped`) instead of crashing import.

## Known-good pins (measured on this host — reproduce exactly)
```
torch==2.14.1+cpu            # CPU build; --index-url https://download.pytorch.org/whl/cpu
torchvision==0.29.1+cpu
transformers==4.51.3         # NOT 5.x (breaks Florence-2: forced_bos_token_id crash)
                              # NOT 4.44 (tokenizers build fails on Py3.13: PyO3 max 3.12)
easyocr==1.7.2               # Reader made LAZY (downloads models on first use, not import)
ultralytics  supervision  timm  einops  matplotlib   # OmniParser companions
pytesseract                  # needs the free Tesseract binary (already on PATH, v5.4.0)
onnxruntime  numpy  pillow  opencv-python            # present
```
Install pattern:
```powershell
D:\new_automation\hojaiga_env\Scripts\python.exe -m pip install --disable-pip-version-check <pkg>==<ver>
```

## The version traps we already hit (do not rediscover them)
- **transformers 5.x** → Florence-2 captioner throws
  `AttributeError: 'Florence2LanguageConfig' object has no attribute 'forced_bos_token_id'`.
- **transformers 4.44** → `tokenizers` tries to compile for Py3.13 and fails
  (`PyO3's maximum supported version (3.12)`). **4.51.3 is the sweet spot.**
- **OmniParser class name** is `Omniparser` (lowercase 'p'); importing `OmniParser` raises a
  swallowed ImportError that looks like "torch missing". `organ_44` now accepts both spellings.
- **OmniParser `util/utils.py`** imported paddleocr + built `easyocr.Reader` at module load
  (hard dependency + surprise download). Both made lazy/optional.

## Local models inventory (all free)
| Need | Model | Where | Cost |
|---|---|---|---|
| Popup/judge reasoning | llama3 | Gatekeeper proxy `:11435` | free, local |
| Icon detection (vision tier) | YOLO (`weights/icon_detect/model.pt`) | `D:\new_automation\OmniParser` | free, on disk |
| Icon captioning | Florence-2-base (`weights/icon_caption_florence`) | local dir | free, on disk |
| OCR | Tesseract 5.4 binary + EasyOCR fallback | Program Files / lazy | free |

## Before adding ANY new dependency, answer in writing
1. Is it free & open-licensed? (paste licence)
2. Does it run fully local with no key/telemetry?
3. Does a wheel exist for **cp313** on Windows, or can it build here?
4. Is there an already-installed lib that does this? (prefer reuse)
5. Can it be imported lazily so its absence never breaks the core loop?
If any answer is "no/unknown", **do not add it** — find a free substitute or implement with stdlib.

## Never do
- `pip install openai / anthropic / google-generativeai / boto3` into the runtime path.
- Call a hosted model endpoint. The only HTTP calls allowed are to `127.0.0.1` services.
- Add a dependency that downloads a model at *runtime* mid-task — pre-warm or bundle it.
