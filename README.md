# MedCaseAgent

Three-stage clinical case report agent: planner, writer, refiner.

This is a clean refactor of the old `helloworld` clinical-agent pipeline. It removes the preprocessing, benchmark conversion, evaluation, and native function-tool loops. Case data is read directly from a JSON, Markdown/text/XML file, or a case folder. Reusable prompt skills in `skills/*/SKILL.md` replace native tool calling.

## Setup

Use the shared environment:

```bash
cd /home/data1/musong/workspace/2026/05/28/MedCaseAgent
/home/data1/musong/workspace/2026/.venv/bin/python -m pip install -e .
```

Set the OpenAI endpoint in `.env`:

```bash
OPENAI_API_KEY=sk-your-key
OPENAI_BASE_URL=https://zxmmm.com/v1
OPENAI_MODEL=qwen3.6-plus
OPENAI_REASONING_EFFORT=low
```

`OPENAI_REASONING_EFFORT` accepts `none`, `minimal`, `low`, `medium`, `high`, and `xhigh`; aliases `med` and `max` map to `medium` and `xhigh`.

The configured provider documents the OpenAI-compatible Chat Completions path:
`https://zxmmm.com/v1/chat/completions`.

## Run

```bash
/home/data1/musong/workspace/2026/.venv/bin/python -m medcase_agent examples/case.json
```

Outputs are written to `runs/<case_id>_<timestamp>/`:

- `01_planner.md`
- `02_writer.md`
- `03_refiner.md`
- `final.md`
- `run_log.json`
- `images/` when supported images are present

Validate input and skills without an API call:

```bash
/home/data1/musong/workspace/2026/.venv/bin/python -m medcase_agent --validate-only examples/case.json
```

## Data Contract

Recommended folder layout:

```text
case_folder/
  case.json
  image1.jpg
  image2.png
```

`case.json` may contain raw fields such as `clinical_data`, `history`, `presentation`, `diagnostics`, `management`, `outcome`, `references`, and `metadata`. Old `*_atoms.json` files are also accepted for compatibility, but they are no longer required.

## Design

- Planner creates a factual manuscript plan from source data and images.
- Writer drafts the manuscript from the approved plan.
- Refiner performs the final clinical, citation, figure, and Markdown audit.
- Skills are plain Markdown operating procedures loaded into stage instructions.
- No model-native function tools are registered, so references and image claims must come from supplied case data and visible images.
