#!/usr/bin/env python3
"""Offline fast-mode evaluation harness skeleton.

Usage:
  python scripts/evaluate_fast_mode.py --project-id <PROJECT_UUID> --dataset <path/to/dataset.json>
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
API_ROOT = SCRIPT_DIR.parent
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

# Optional provider dependencies used during app import.
sys.modules.setdefault("voyageai", SimpleNamespace(Client=lambda *args, **kwargs: None))
sys.modules.setdefault("supabase", SimpleNamespace(create_client=lambda *args, **kwargs: None))
sys.modules.setdefault("pdf2image", SimpleNamespace(convert_from_bytes=lambda *args, **kwargs: []))

from app.database.session import SessionLocal  # noqa: E402
from app.services.core.agent import run_agent_query_fast  # noqa: E402


@dataclass
class EvalCase:
    query: str
    expected_page_ids: list[str] = field(default_factory=list)
    expected_sheet_numbers: list[str] = field(default_factory=list)
    expected_sheet_titles: list[str] = field(default_factory=list)
    expected_keywords: list[str] = field(default_factory=list)


def _normalize(value: str) -> str:
    return " ".join("".join(ch.lower() if ch.isalnum() else " " for ch in str(value or "")).split())


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _load_cases(dataset_path: Path) -> list[EvalCase]:
    raw = json.loads(dataset_path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("Dataset must be a JSON array.")

    cases: list[EvalCase] = []
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"Dataset row {idx} is not an object.")
        query = str(item.get("query") or "").strip()
        if not query:
            raise ValueError(f"Dataset row {idx} is missing query.")
        cases.append(
            EvalCase(
                query=query,
                expected_page_ids=[str(v).strip() for v in item.get("expected_page_ids", []) if str(v).strip()],
                expected_sheet_numbers=[str(v).strip() for v in item.get("expected_sheet_numbers", []) if str(v).strip()],
                expected_sheet_titles=[str(v).strip() for v in item.get("expected_sheet_titles", []) if str(v).strip()],
                expected_keywords=[str(v).strip() for v in item.get("expected_keywords", []) if str(v).strip()],
            )
        )
    return cases


def _extract_selected_ids(trace: list[dict[str, Any]]) -> list[str]:
    for step in trace:
        if step.get("type") != "tool_call":
            continue
        if step.get("tool") != "select_pages":
            continue
        tool_input = step.get("input", {})
        if not isinstance(tool_input, dict):
            continue
        page_ids = tool_input.get("page_ids", [])
        if isinstance(page_ids, list):
            return [str(page_id).strip() for page_id in page_ids if str(page_id).strip()]
    return []


def _extract_page_names(trace: list[dict[str, Any]], selected_ids: list[str]) -> list[str]:
    id_to_name: dict[str, str] = {}
    for step in trace:
        if step.get("type") != "tool_result" or step.get("tool") != "select_pages":
            continue
        result = step.get("result", {})
        if not isinstance(result, dict):
            continue
        pages = result.get("pages", [])
        if not isinstance(pages, list):
            continue
        for page in pages:
            if not isinstance(page, dict):
                continue
            page_id = str(page.get("page_id") or "").strip()
            page_name = str(page.get("page_name") or "").strip()
            if page_id and page_name and page_id not in id_to_name:
                id_to_name[page_id] = page_name
    return [id_to_name.get(page_id, page_id) for page_id in selected_ids]


def _extract_fast_trace_payload(trace: list[dict[str, Any]]) -> dict[str, Any]:
    for step in reversed(trace):
        if step.get("type") != "tool_result":
            continue
        if step.get("tool") != "fast_mode_trace":
            continue
        result = step.get("result", {})
        if isinstance(result, dict):
            return result
    return {}


def _precision_at_k(predicted_ids: list[str], expected_ids: list[str], k: int) -> float | None:
    if not expected_ids:
        return None
    top_k = predicted_ids[:k]
    if not top_k:
        return 0.0
    relevant = sum(1 for page_id in top_k if page_id in set(expected_ids))
    return relevant / float(k)


def _exact_title_hit(predicted_names: list[str], expected_titles: list[str], k: int) -> bool | None:
    if not expected_titles:
        return None
    top_k = [_normalize(name) for name in predicted_names[:k]]
    expected = [_normalize(title) for title in expected_titles if _normalize(title)]
    for title in expected:
        if any(title == name or title in name for name in top_k):
            return True
    return False


def _sheet_number_hit(predicted_names: list[str], expected_sheet_numbers: list[str], k: int) -> bool | None:
    if not expected_sheet_numbers:
        return None
    top_k = [_normalize(name) for name in predicted_names[:k]]
    expected = [_normalize(num) for num in expected_sheet_numbers if _normalize(num)]
    for number in expected:
        if any(number in name for name in top_k):
            return True
    return False


def _keyword_hit_count(predicted_names: list[str], expected_keywords: list[str], k: int) -> int | None:
    if not expected_keywords:
        return None
    top_k = " ".join(_normalize(name) for name in predicted_names[:k])
    return sum(1 for keyword in expected_keywords if _normalize(keyword) and _normalize(keyword) in top_k)


async def _replay_case(project_id: str, case: EvalCase) -> dict[str, Any]:
    db = SessionLocal()
    try:
        done_event: dict[str, Any] | None = None
        async for event in run_agent_query_fast(
            db=db,
            project_id=project_id,
            query=case.query,
            history_messages=[],
            viewing_context=None,
        ):
            if event.get("type") == "done":
                done_event = event

        if not isinstance(done_event, dict):
            raise RuntimeError("Fast mode did not produce a done event.")

        trace = done_event.get("trace", [])
        if not isinstance(trace, list):
            trace = []

        selected_page_ids = _extract_selected_ids(trace)
        selected_page_names = _extract_page_names(trace, selected_page_ids)
        fast_trace_payload = _extract_fast_trace_payload(trace)

        usage = done_event.get("usage", {})
        if not isinstance(usage, dict):
            usage = {}

        return {
            "query": case.query,
            "selected_page_ids": selected_page_ids,
            "selected_page_names": selected_page_names,
            "usage": {
                "input_tokens": _to_int(usage.get("inputTokens", 0)),
                "output_tokens": _to_int(usage.get("outputTokens", 0)),
            },
            "trace_payload": fast_trace_payload,
        }
    finally:
        db.close()


async def _run_eval(project_id: str, cases: list[EvalCase], k: int) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    precision_values: list[float] = []
    exact_title_values: list[bool] = []
    sheet_number_values: list[bool] = []
    total_input_tokens = 0
    total_output_tokens = 0

    for case in cases:
        replay = await _replay_case(project_id=project_id, case=case)
        predicted_ids = replay["selected_page_ids"]
        predicted_names = replay["selected_page_names"]

        precision = _precision_at_k(predicted_ids, case.expected_page_ids, k)
        exact_title = _exact_title_hit(predicted_names, case.expected_sheet_titles, k)
        sheet_number_hit = _sheet_number_hit(predicted_names, case.expected_sheet_numbers, k)
        keyword_hit_count = _keyword_hit_count(predicted_names, case.expected_keywords, k)

        if precision is not None:
            precision_values.append(precision)
        if exact_title is not None:
            exact_title_values.append(exact_title)
        if sheet_number_hit is not None:
            sheet_number_values.append(sheet_number_hit)

        total_input_tokens += replay["usage"]["input_tokens"]
        total_output_tokens += replay["usage"]["output_tokens"]

        rows.append(
            {
                "query": case.query,
                "predicted_page_ids_top_k": predicted_ids[:k],
                "predicted_sheet_names_top_k": predicted_names[:k],
                "precision_at_k": precision,
                "exact_title_hit_present_top_k": exact_title,
                "expected_sheet_number_hit_top_k": sheet_number_hit,
                "expected_keyword_hit_count_top_k": keyword_hit_count,
                "token_cost": replay["usage"],
            }
        )

    def _avg(values: list[float]) -> float | None:
        if not values:
            return None
        return sum(values) / float(len(values))

    return {
        "summary": {
            "case_count": len(cases),
            "k": k,
            "precision_at_k_avg": _avg(precision_values),
            "exact_title_hit_rate": _avg([1.0 if v else 0.0 for v in exact_title_values]),
            "sheet_number_hit_rate": _avg([1.0 if v else 0.0 for v in sheet_number_values]),
            "token_cost": {
                "input_tokens": total_input_tokens,
                "output_tokens": total_output_tokens,
                "total_tokens": total_input_tokens + total_output_tokens,
            },
        },
        "results": rows,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay fast-mode queries and compute offline metrics.")
    parser.add_argument("--project-id", required=True, help="Project UUID to replay against.")
    parser.add_argument("--dataset", required=True, help="Path to JSON dataset file.")
    parser.add_argument("--k", type=int, default=4, help="Top-k cutoff for metrics (default: 4).")
    parser.add_argument("--max-cases", type=int, default=0, help="Optional max number of cases to run.")
    parser.add_argument("--out", default="", help="Optional output file path for JSON results.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dataset_path = Path(args.dataset).resolve()
    if not dataset_path.exists():
        print(f"Dataset not found: {dataset_path}", file=sys.stderr)
        return 1

    try:
        cases = _load_cases(dataset_path)
    except Exception as exc:
        print(f"Failed to load dataset: {exc}", file=sys.stderr)
        return 1

    if args.max_cases and args.max_cases > 0:
        cases = cases[: args.max_cases]

    result = asyncio.run(_run_eval(project_id=args.project_id, cases=cases, k=max(1, int(args.k))))
    output = json.dumps(result, indent=2)

    if args.out:
        out_path = Path(args.out).resolve()
        out_path.write_text(output, encoding="utf-8")
        print(f"Wrote evaluation report to: {out_path}")
    else:
        print(output)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
