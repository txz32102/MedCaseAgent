# MedCaseAgent

Three-stage clinical case report agent: planner, writer, refiner.

This is a clean refactor of the old `helloworld` clinical-agent pipeline. It removes the preprocessing, benchmark conversion, and evaluation stages. Case data is read directly from a JSON, Markdown/text/XML file, or a case folder. Reusable prompt skills in `skills/*/SKILL.md` provide stage operating procedures, while optional `skills/*/tools.py` modules provide native function tools.

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
MEDCASE_ENABLE_TOOLS=true
MEDCASE_MAX_TOOL_TURNS=8
MEDCASE_CURATE_CITATIONS=true
MEDCASE_TARGET_REFERENCES=10
```

`OPENAI_REASONING_EFFORT` accepts `none`, `minimal`, `low`, `medium`, `high`, and `xhigh`; aliases `med` and `max` map to `medium` and `xhigh`.

The configured provider documents the OpenAI-compatible Chat Completions path:
`https://zxmmm.com/v1/chat/completions`.

## Run

```bash
/home/data1/musong/workspace/2026/.venv/bin/python -m medcase_agent examples/case.json
```

Real copied case example:

```bash
/home/data1/musong/workspace/2026/.venv/bin/python -m medcase_agent examples/41799793/case.json
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

Images may sit beside `case.json` or inside `imgs/`, `images/`, or `figures/`.

## Skills And Tools

Skill folders may contain prompt guidance only, or prompt guidance plus native tools:

```text
skills/
  tool_use_policy/
    SKILL.md
    tools.py
```

`SKILL.md` is loaded into the stage instructions. `tools.py` may define `TOOL_SCHEMAS` and `AVAILABLE_TOOLS`; those functions are registered as model-native tools when `MEDCASE_ENABLE_TOOLS=true`.

## Design

- Planner creates a factual manuscript plan from source data and images.
- Writer drafts the manuscript from the approved plan.
- Refiner performs the final clinical, citation, figure, and Markdown audit.
- Skills are plain Markdown operating procedures loaded into stage instructions.
- Native function tools are discovered from `skills/*/tools.py` when `MEDCASE_ENABLE_TOOLS=true`. The bundled `tool_use_policy` skill registers `search_pubmed`, `fetch_ama_citations`, `search_clingen_by_keyword`, and `fetch_clingen_variant_data`.
- When `MEDCASE_CURATE_CITATIONS=true`, the agent runs a deterministic PubMed/DOI citation-curation pre-stage before planner/writer/refiner.
- The disease-importance/RAG tool from `helloworld` is intentionally not implemented yet.
- Image claims must still come from supplied case data and visible images; the old MedGemma and composite-figure tools are not pulled into this lightweight refactor.
