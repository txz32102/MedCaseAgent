---
name: tool_use_policy
description: Use native function tools only for verified external evidence.
when_to_use: Use when PubMed, DOI citation formatting, or ClinGen evidence may be needed.
---
Tool rules:
- When native tools are available, use `search_pubmed` only for general medical background, diagnostic criteria, treatment context, or literature comparison; do not use it to alter patient-specific facts.
- When native tools are available, use `fetch_ama_citations` only with DOI values verified from supplied source data or `search_pubmed` results.
- When native tools are available, use `search_clingen_by_keyword` and `fetch_clingen_variant_data` only when the source case explicitly mentions a genetic variant or mutation.
- If native tool calling is disabled, use only references and evidence supplied in the source case.
- Do not invent references, DOI values, PMIDs, PMCID values, guideline names, authors, journal names, or years.
- The disease-importance/RAG tool is intentionally unavailable. Do not claim "first reported case", exact rarity, or absence of prior reports unless that claim is directly supported by supplied source material or verified tool output.
