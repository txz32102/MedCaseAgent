from __future__ import annotations

import html
import os
import re
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Any

import requests


PUBMED_TOOL_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "search_pubmed",
        "description": (
            "Find real peer-reviewed medical literature candidates in PubMed. "
            "Use strict Boolean or keyword queries, not natural-language questions. "
            "Returned DOI/PMID metadata must be verified before any citation is used."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Medical search query, for example: essential thrombocythemia AND gallbladder.",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of papers to return.",
                    "default": 10,
                },
            },
            "required": ["query"],
        },
    },
}

FETCH_CITATION_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "fetch_ama_citations",
        "description": (
            "Fetch AMA-formatted citation strings for selected DOIs. "
            "Use only DOI values returned by verified literature searches or supplied source data."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "dois": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Exact DOI strings without surrounding prose.",
                },
            },
            "required": ["dois"],
        },
    },
}

CLINGEN_SEARCH_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "search_clingen_by_keyword",
        "description": (
            "Resolve a gene or variant mention to a ClinGen evidence repository UUID. "
            "Use only when the case source explicitly mentions a genetic variant or mutation."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Gene and variant name, for example: BRAF V600E.",
                },
            },
            "required": ["query"],
        },
    },
}

CLINGEN_FETCH_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "fetch_clingen_variant_data",
        "description": (
            "Fetch expert-curated ClinGen evidence for a UUID returned by "
            "search_clingen_by_keyword."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "uuid": {
                    "type": "string",
                    "description": "Exact ClinGen UUID returned by search_clingen_by_keyword.",
                },
            },
            "required": ["uuid"],
        },
    },
}


TOOL_SCHEMAS: list[dict[str, Any]] = [
    PUBMED_TOOL_SCHEMA,
    FETCH_CITATION_SCHEMA,
    CLINGEN_SEARCH_SCHEMA,
    CLINGEN_FETCH_SCHEMA,
]


def fetch_ama_citations(dois: str | list[str], **kwargs: Any) -> str:
    if isinstance(dois, str):
        dois = [dois]

    headers = {"Accept": "text/x-bibliography; style=american-medical-association"}
    formatted_citations: list[str] = []

    for index, doi in enumerate(dois, start=1):
        clean_doi = doi.replace("https://doi.org/", "").replace("doi:", "").strip()
        if not clean_doi:
            continue

        try:
            response = requests.get(
                f"https://doi.org/{clean_doi}",
                headers=headers,
                timeout=10,
            )
            response.raise_for_status()
            raw_citation = response.content.decode("utf-8", errors="replace").strip()
            raw_citation = html.unescape(raw_citation)
            cleaned_citation = re.sub(r"^\[?\d+\]?\.?\s*", "", raw_citation)
            cleaned_citation = re.sub(r"\s*,\s*ed\.\s*", " ", cleaned_citation)
            cleaned_citation = cleaned_citation.replace("â", "-")
            formatted_citations.append(f"{index}. {cleaned_citation}")
        except Exception as exc:
            formatted_citations.append(
                f"{index}. [Error fetching AMA citation for DOI {clean_doi}: {exc}]"
            )

    if not formatted_citations:
        return "No DOI values were provided."
    return "\n\n".join(formatted_citations)


def search_pubmed(
    query: str,
    max_results: int = 10,
    context: dict[str, Any] | None = None,
    **kwargs: Any,
) -> str:
    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    api_key = os.environ.get("NCBI_API_KEY")
    case_id = str((context or {}).get("case_id") or "")

    clean_query = re.sub(r"\b(doi|pmid)\b", "", query, flags=re.IGNORECASE).strip()
    clean_query = re.sub(r"\s+", " ", clean_query)
    words = clean_query.split()
    if not words:
        return "No PubMed query terms were provided."

    max_results = max(1, min(int(max_results or 10), 20))
    pmids: list[str] = []
    search_notes: list[str] = []

    while words:
        current_query = " ".join(words)
        search_params: dict[str, Any] = {
            "db": "pubmed",
            "term": current_query,
            "retmode": "json",
            "retmax": max_results + 2,
            "sort": "date",
        }
        if api_key:
            search_params["api_key"] = api_key

        response = requests.get(
            f"{base_url}/esearch.fcgi",
            params=search_params,
            timeout=10,
        )
        response.raise_for_status()
        pmids = response.json().get("esearchresult", {}).get("idlist", [])
        if case_id and case_id in pmids:
            pmids.remove(case_id)
        pmids = pmids[:max_results]
        if pmids:
            if current_query != clean_query:
                search_notes.append(f"Query relaxed to: {current_query}")
            break
        if len(words) == 1:
            break
        search_notes.append(f"No PubMed results for: {current_query}")
        words = words[: max(1, len(words) // 2)]

    if not pmids:
        return f"No results found on PubMed for query: {query!r}."

    fetch_params: dict[str, Any] = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "xml",
    }
    if api_key:
        fetch_params["api_key"] = api_key

    response = requests.get(
        f"{base_url}/efetch.fcgi",
        params=fetch_params,
        timeout=10,
    )
    response.raise_for_status()

    root = ET.fromstring(response.content)
    formatted_results: list[str] = []

    for article in root.findall(".//PubmedArticle"):
        pmid = _extract_element_text(article.find(".//MedlineCitation/PMID")) or "Unknown PMID"
        title = _extract_element_text(article.find(".//ArticleTitle")) or "No title"
        journal = _extract_element_text(article.find(".//Journal/Title")) or "Unknown journal"
        pub_year = _publication_year(article)

        abstract_parts = []
        for abstract_text in article.findall(".//AbstractText"):
            label = abstract_text.attrib.get("Label")
            text = _extract_element_text(abstract_text)
            if not text:
                continue
            abstract_parts.append(f"{label}: {text}" if label else text)
        abstract = " ".join(abstract_parts).strip() or "No abstract available."

        doi = "No DOI"
        pmcid = "No PMCID"
        for article_id in article.findall(".//PubmedData/ArticleIdList/ArticleId"):
            value = _extract_element_text(article_id)
            if article_id.get("IdType") == "doi" and value:
                doi = value
            elif article_id.get("IdType") == "pmc" and value:
                pmcid = value

        formatted_results.append(
            f"Title: {title}\n"
            f"Journal: {journal} ({pub_year or 'Unknown year'})\n"
            f"PMID: {pmid} | PMCID: {pmcid} | DOI: {doi}\n"
            f"Abstract: {abstract}"
        )

    if search_notes:
        return "\n".join(f"Note: {note}" for note in search_notes) + "\n\n" + "\n---\n".join(
            formatted_results
        )
    return "\n---\n".join(formatted_results)


def search_clingen_by_keyword(query: str, **kwargs: Any) -> dict[str, Any]:
    encoded_query = urllib.parse.quote(query)
    esearch_url = (
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        f"?db=clinvar&term={encoded_query}&retmode=json"
    )

    esearch_resp = requests.get(esearch_url, timeout=10)
    esearch_resp.raise_for_status()
    esearch_data = esearch_resp.json()

    id_list = esearch_data.get("esearchresult", {}).get("idlist", [])
    if not id_list:
        return {"status": "error", "message": f"No ClinVar variant found for query: {query!r}"}

    clinvar_id = id_list[0]
    clingen_search_url = (
        "https://erepo.genome.network/evrepo/api/summary/classifications"
        f"?columns=cvId&values={clinvar_id}&matchTypes=exact"
    )
    clingen_resp = requests.get(clingen_search_url, timeout=10)
    clingen_resp.raise_for_status()
    clingen_data = clingen_resp.json()

    records = (
        clingen_data
        if isinstance(clingen_data, list)
        else clingen_data.get("data", clingen_data.get("results", []))
    )
    if not records:
        return {
            "status": "error",
            "message": f"ClinVar ID {clinvar_id} exists, but no ClinGen curation was found.",
        }

    uuid = records[0].get("uuid")
    if not uuid:
        return {"status": "error", "message": "ClinGen record found, but UUID is missing."}

    return {
        "status": "success",
        "matches_found": len(records),
        "clinvar_id": clinvar_id,
        "uuid": uuid,
    }


def fetch_clingen_variant_data(uuid: str, **kwargs: Any) -> dict[str, Any]:
    api_endpoint = (
        "https://erepo.genome.network/evrepo/api/summary/classification/"
        f"{uuid}/doc/sepio/version/1.0.0"
    )
    response = requests.get(api_endpoint, timeout=10)
    response.raise_for_status()
    raw_json = response.json()

    data_node = raw_json.get("data", {})
    condition = data_node.get("condition", {}).get("label", "Unknown condition")
    classification = data_node.get("statementOutcome", {}).get("label", "Unknown classification")
    variant_node = data_node.get("variant", {}).get("relatedIdentifier", [{}])
    variant_name = variant_node[0].get("label", "Unknown variant") if variant_node else "Unknown variant"
    evidence_list: list[str] = []
    _extract_evidence_comments(data_node, evidence_list)

    return {
        "variant": variant_name,
        "condition": condition,
        "classification": classification,
        "evidence_bullets": evidence_list,
    }


def _extract_element_text(element: ET.Element | None) -> str:
    if element is None:
        return ""
    return " ".join(part.strip() for part in element.itertext() if part and part.strip()).strip()


def _publication_year(article: ET.Element) -> str:
    year = _extract_element_text(article.find(".//PubDate/Year"))
    if year:
        return year
    medline_date = _extract_element_text(article.find(".//PubDate/MedlineDate"))
    match = re.search(r"\b(19|20)\d{2}\b", medline_date)
    return match.group(0) if match else ""


def _extract_evidence_comments(data: Any, comments: list[str]) -> None:
    if isinstance(data, dict):
        for key, value in data.items():
            if key == "comments" and isinstance(value, str):
                comments.append(value)
            else:
                _extract_evidence_comments(value, comments)
    elif isinstance(data, list):
        for item in data:
            _extract_evidence_comments(item, comments)


AVAILABLE_TOOLS = {
    "search_pubmed": search_pubmed,
    "fetch_ama_citations": fetch_ama_citations,
    "search_clingen_by_keyword": search_clingen_by_keyword,
    "fetch_clingen_variant_data": fetch_clingen_variant_data,
}
