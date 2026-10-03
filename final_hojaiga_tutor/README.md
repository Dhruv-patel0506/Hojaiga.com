# Hojaiga Tutor

AI tutor mode. Paste Gemini-generated code into the matching file below.

## Layout

```
final hojaiga tutor/
  app/          UI + entry point (main.py)
  services/     Gemini API client, tutor session logic
  prompts/      System prompts / lesson templates (.txt, .md)
  config/       settings, API key loading
  data/         lessons, history, user progress
  tests/        test files
```

## Setup

```
pip install -r requirements.txt
python app/main.py
```

## Run tests

```
pytest
```
