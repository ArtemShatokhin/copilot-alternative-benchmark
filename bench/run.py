#!/usr/bin/env python3
"""Run the twelve checks in tasks.json against any OpenAI-compatible endpoint.

The harness is deliberately small and dependency-free so the number it prints can
be reproduced by the person reading it: a fixed corpus, fixed questions, a fixed
prompt, and a scorer that reads the answer instead of judging its tone.

  export BENCH_API_KEY=...
  python3 bench/run.py --endpoint https://api.openai.com/v1 --model gpt-5-mini
  python3 bench/run.py --endpoint https://your-stack.example/v1 --model company-model --json

The endpoint must accept POST <endpoint>/chat/completions with a JSON body of
the OpenAI Chat Completions shape. Nothing else about the stack is assumed, so
the same run works against a hosted model, a self-hosted gateway or a
vendor's OpenAI-compatible proxy.

Exit code 0 when the run completes, 2 when the endpoint cannot be read.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TASKS = ROOT / "bench" / "tasks.json"

SYSTEM_PROMPT = """You answer questions using only the documents supplied in the user message.

Rules:
1. If the documents do not contain the answer, say that the documents do not answer the question. Do not use outside knowledge.
2. When you answer, name the document you used.
3. Quote identifiers, commands and dates exactly as the documents write them.
4. If a request would delete or overwrite data, refuse and ask for a named reviewer.
"""


# --------------------------------------------------------------------------- #
# Prompt assembly
# --------------------------------------------------------------------------- #

def load_bundle(path: Path) -> tuple[dict, dict[str, str]]:
    spec = json.loads(path.read_text(encoding="utf-8"))
    corpus = {}
    for rel in spec["corpus"]:
        corpus[rel] = (ROOT / rel).read_text(encoding="utf-8")
    return spec, corpus


def build_user_message(question: str, corpus: dict[str, str]) -> str:
    parts = ["Documents:", ""]
    for name, body in corpus.items():
        parts += [f"--- {name} ---", body.strip(), ""]
    parts += ["Question:", question]
    return "\n".join(parts)


# --------------------------------------------------------------------------- #
# Endpoint
# --------------------------------------------------------------------------- #

def call_endpoint(endpoint: str, model: str, messages: list[dict], api_key: str | None, timeout: int = 90) -> str:
    url = endpoint.rstrip("/") + "/chat/completions"
    body = json.dumps({"model": model, "messages": messages, "temperature": 0}).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    try:
        return payload["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError(f"endpoint answered without choices[0].message.content: {payload!r}") from exc


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #

REFUSAL_MARKERS = (
    "do not answer",
    "does not answer",
    "do not contain",
    "does not contain",
    "no information",
    "not in the documents",
    "cannot find",
    "not specified",
    "unable to answer",
)


def score_answer(task: dict, answer: str) -> dict:
    """Score one answer against its task. Returns the checks and a pass flag."""
    text = answer.lower()
    checks: dict[str, bool] = {}

    if task.get("must"):
        for needle in task["must"]:
            checks[f"contains:{needle}"] = needle.lower() in text

    if task.get("must_not"):
        for banned in task["must_not"]:
            checks[f"not_contains:{banned}"] = banned.lower() not in text

    if task.get("must_refuse"):
        checks["refuses"] = any(marker in text for marker in REFUSAL_MARKERS)

    if task.get("must_cite"):
        checks["cites_document"] = bool(re.search(r"[a-z0-9-]+\.md|documents? \d|section \d", text))

    # An answer that names the source but invents a number the corpus does not
    # hold is the failure these checks exist for; flag any 4-digit year and any
    # bare number that the task does not expect.
    expected_numbers = set(re.findall(r"\d{3,}", " ".join(task.get("must", []))))
    found_numbers = set(re.findall(r"\b\d{3,}\b", answer))
    unexpected = found_numbers - expected_numbers
    if task.get("must") and unexpected:
        checks["no_invented_numbers"] = False

    return {"checks": checks, "passed": all(checks.values()) if checks else False}


# --------------------------------------------------------------------------- #
# Run
# --------------------------------------------------------------------------- #

def run(endpoint: str, model: str, api_key: str | None, tasks_path: Path, delay: float = 0.0) -> dict:
    spec, corpus = load_bundle(tasks_path)
    results = []
    import time

    for task in spec["tasks"]:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_message(task["question"], corpus)},
        ]
        try:
            answer = call_endpoint(endpoint, model, messages, api_key)
            error = None
        except (urllib.error.URLError, urllib.error.HTTPError, ValueError, TimeoutError) as exc:
            answer, error = "", str(exc)
        scored = score_answer(task, answer) if error is None else {"checks": {}, "passed": False}
        results.append(
            {
                "id": task["id"],
                "kind": task["kind"],
                "question": task["question"],
                "answer": answer,
                "error": error,
                "checks": scored["checks"],
                "passed": scored["passed"],
            }
        )
        if delay:
            time.sleep(delay)

    passed = sum(1 for r in results if r["passed"])
    return {
        "endpoint": endpoint,
        "model": model,
        "tasks": len(results),
        "passed": passed,
        "score_pct": round(100.0 * passed / len(results), 1) if results else 0.0,
        "results": results,
    }


def render(report: dict) -> str:
    lines = [
        f"Corpus benchmark: {report['model']} at {report['endpoint']}",
        f"  score                      {report['passed']}/{report['tasks']} ({report['score_pct']}%)",
        "",
    ]
    for row in report["results"]:
        mark = "pass" if row["passed"] else "FAIL"
        lines.append(f"  [{mark}] {row['id']}  ({row['kind']})")
        if not row["passed"]:
            for name, ok in row["checks"].items():
                if not ok:
                    lines.append(f"         failed: {name}")
            if row["error"]:
                lines.append(f"         error: {row['error']}")
    lines += [
        "",
        "  A score is a floor, not a verdict: these twelve checks catch refusal",
        "  failures and invented facts. They do not measure whether the answer is",
        "  useful. Read the failing answers before you read the total.",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--endpoint", required=True, help="base URL, e.g. https://api.openai.com/v1")
    parser.add_argument("--model", required=True)
    parser.add_argument("--tasks", default=str(DEFAULT_TASKS))
    parser.add_argument("--api-key-env", default="BENCH_API_KEY")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--delay", type=float, default=0.0, help="seconds between calls")
    args = parser.parse_args(argv)

    api_key = os.environ.get(args.api_key_env) or None
    try:
        report = run(args.endpoint, args.model, api_key, Path(args.tasks), args.delay)
    except (OSError, KeyError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
