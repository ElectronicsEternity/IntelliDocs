"""One paid, cached hierarchy test; never ingest or alter document records."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from openai import OpenAI
from pypdf import PdfReader, PdfWriter
from app.config import settings
from app.indexing.document_profiler import DocumentProfiler
from app.indexing.document_profile_validator import DocumentProfileValidator, ALLOWED_NODE_TYPES
from app.services.usage.ai_usage import build_record, tracked_ai_call

PAGES = [55, 56, 57, 58, 59, 112, 113]
FOLDER = ROOT / "logs/diagnostics/hierarchy_references_v1"


# Save private artifacts individually so a completed paid call is never repeated.
def save(name, value):
    (FOLDER / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


# Walk real nodes while retaining the hierarchy path needed for reverse lookup.
def walk(node, ancestors=(), path="DOCUMENT"):
    yield node, ancestors, path
    for index, child in enumerate(node.get("children", [])):
        yield from walk(child, ancestors + (node,), f"{path}.children[{index}]")


# Normalize punctuation/layout for local matching, without altering saved JSON.
def key(value):
    return re.sub(r"[^a-z0-9]", "", value.lower())


# Parenthesis boundaries are structural: (1A) must never equal (1)(a).
def child_key(value):
    return re.sub(r"\s+", "", value).lower().rstrip(".")


def validate_and_resolve(tree):
    errors = list(DocumentProfileValidator().validate(
        tree, expected_language="English", expected_page_count=len(PAGES),
        require_mapping_metadata=True, require_routing_metadata=True).errors)
    entries = list(walk(tree))
    links, unresolved = [], []
    for node, ancestors, path in entries:
        references = node.get("references")
        if not isinstance(references, list):
            errors.append(f"{path}: references must be an array")
            continue
        for reference in references:
            if not isinstance(reference, dict) or set(reference) != {"node_type", "identifier", "sub_identifier"}:
                errors.append(f"{path}: invalid reference fields")
                continue
            if not isinstance(reference["node_type"], str) or reference["node_type"] not in ALLOWED_NODE_TYPES or not isinstance(reference["identifier"], str):
                errors.append(f"{path}: invalid reference target")
                continue
            if reference["sub_identifier"] is not None and not isinstance(reference["sub_identifier"], str):
                errors.append(f"{path}: sub_identifier must be text or null")
                continue
            matches = []
            for target, parents, target_path in entries:
                # The target base can be an ancestor of a subsection or clause.
                chain = parents + (target,)
                for position, base in enumerate(chain):
                    if base["type"] != reference["node_type"] or key(base["identifier"]) != key(reference["identifier"]):
                        continue
                    child_path = "".join(item["identifier"] for item in chain[position + 1:])
                    if child_key(child_path) == child_key(reference["sub_identifier"] or ""):
                        matches.append(target_path)
            link = {"source_path": path, "reference": reference, "target_paths": matches}
            # Ambiguous or absent destinations remain unresolved, never guessed.
            (links if len(matches) == 1 else unresolved).append(link)
    schedule_tables = {path for node, parents, path in entries
                       if node["type"] == "TABLE" and any(
                           item["type"] == "SCHEDULE" and "firstschedule" in key(item["identifier"] + item["title"])
                           for item in parents)}
    expected = {("60", "(3)"), ("60A", "(3)"), ("60C", "(2A)"),
                ("60D", "(3)"), ("60D", "(4)"), ("60J", None)}
    extracted = {(ref["identifier"], ref["sub_identifier"])
                 for node, _, path in entries if path in schedule_tables
                 for ref in node.get("references", []) if isinstance(ref, dict)}
    missing = sorted(expected - extracted, key=str)
    if missing:
        errors.append(f"First Schedule table missing expected references: {missing}")
    # Parent retrieval includes incoming references to any of its descendants.
    section_paths = [path for node, _, path in entries if node["type"] == "SECTION" and key(node["identifier"]) == "60a"]
    reverse = [link for link in links if any(
        target == section or target.startswith(section + ".children[")
        for target in link["target_paths"] for section in section_paths)]
    found = any(link["source_path"] in schedule_tables and link["reference"]["sub_identifier"] == "(3)" for link in reverse)
    if not found:
        errors.append("Reverse lookup for Section 60A did not find the First Schedule table")
    return {"errors": errors, "passed": not errors, "resolved_links": links,
            "unresolved_links": unresolved, "section60a_incoming_links": reverse,
            "first_schedule_60a3_reverse_lookup": found, "node_count": len(entries)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true", help="Authorize one paid request if no cache exists")
    args = parser.parse_args()
    FOLDER.mkdir(parents=True, exist_ok=True)
    pdf = ROOT / "tmp/pdfs/akta-ingestion-audit/Akta_Kerja_1955_Akta_265.pdf"
    reader, writer = PdfReader(pdf), PdfWriter()
    sections = []
    for local_page, original_page in enumerate(PAGES, 1):
        writer.add_page(reader.pages[original_page - 1])
        sections.append(f"[[PAGE_LABEL: {local_page}]]\n" + reader.pages[original_page - 1].extract_text())
    cropped = FOLDER / "selected_pages.pdf"
    writer.write(cropped)
    prompt = DocumentProfiler._build_prompt(None, "\n\n".join(sections), "English", len(PAGES))
    # Partial pages cannot justify fabricating missing parent sections or targets.
    prompt += "\nTEST SCOPE: This PDF is a non-contiguous excerpt. Profile only supplied structure. " \
              "Do not invent absent parents for leading continuation fragments. " \
              "Use PAGE_LABEL 1..7, not original printed page numbers. " \
              "References to other documents in the Second Schedule must not become internal links.\n"
    request = {"model": settings.HIERARCHY_PROFILE_MODEL,
               "reasoning": {"effort": settings.HIERARCHY_REASONING_EFFORT},
               "max_output_tokens": 12000,
               "input": [{"role": "user", "content": [
                   {"type": "input_text", "text": prompt},
                   {"type": "input_file", "filename": "selected_pages.pdf",
                    "file_data": "data:application/pdf;base64," + base64.b64encode(cropped.read_bytes()).decode()}]}]}
    identity = {"pdf_hash": hashlib.sha256(pdf.read_bytes()).hexdigest(), "original_pages": PAGES,
                "prompt_hash": hashlib.sha256(prompt.encode()).hexdigest(), "model": request["model"],
                "reasoning": request["reasoning"], "max_output_tokens": request["max_output_tokens"]}
    save("page_mapping.json", {str(i): page for i, page in enumerate(PAGES, 1)})
    (FOLDER / "prompt.txt").write_text(prompt, encoding="utf-8")
    cached = FOLDER / "response.json"
    if cached.exists():
        result = json.loads(cached.read_text(encoding="utf-8"))
        if result["identity"] != identity:
            raise RuntimeError("Cached inputs differ; refusing another paid call")
    else:
        if not args.run:
            print("Prepared experiment; use --run for one paid call")
            return
        if (FOLDER / "request_started.json").exists():
            raise RuntimeError("An earlier request may have been billed; refusing automatic repeat")
        save("request_started.json", identity)
        print(f"Requesting {request['model']} High for {len(PAGES)} pages; retries disabled", flush=True)
        # Use existing per-user usage tracking, but never alter ingestion records.
        client = OpenAI(api_key=settings.OPENAI_API_KEY, max_retries=0, timeout=600)
        response = tracked_ai_call(lambda: client.responses.create(**request),
                                   activity="hierarchy_references_experiment", model=request["model"],
                                   user_id="3a9eaaa6-1dee-4be7-b78c-371e16944a01",
                                   document_id="69b2ea9c-594c-47fc-8db8-76a399ab6140")
        usage = build_record(response, activity="hierarchy_references_experiment", model=request["model"],
                             user_id="3a9eaaa6-1dee-4be7-b78c-371e16944a01",
                             document_id="69b2ea9c-594c-47fc-8db8-76a399ab6140")
        result = {"identity": identity, "response": response.model_dump(mode="json"), "usage": usage}
        save("response.json", result)
    raw = result["response"]
    if raw.get("status") != "completed":
        raise RuntimeError("Incomplete response saved; no automatic retry")
    text = "".join(part.get("text", "") for output in raw.get("output", [])
                   for part in output.get("content", []) if part.get("type") == "output_text")
    tree = json.loads(text)
    save("hierarchy.json", tree)
    report = validate_and_resolve(tree)
    report["usage"] = result["usage"]
    save("validation.json", report)
    print(json.dumps({key: value for key, value in report.items()
                      if key not in {"resolved_links", "unresolved_links"}}, indent=2, default=str), flush=True)


if __name__ == "__main__":
    main()
