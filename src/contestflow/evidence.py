"""Typed metric definitions and exact run-to-table provenance."""

from __future__ import annotations

import csv
import io

from .core import (
    FlowError,
    digest,
    digest_bytes,
    identity,
    journal,
    local,
    read_json,
    require_mutable,
    write_json,
    write_text,
)
from .runner import current_runs


def context(root):
    definitions = read_json(local(root, "evidence/metrics.json"))
    if not definitions.get("metrics"):
        raise FlowError("Define metrics in evidence/metrics.json before comparing")
    for name, spec in definitions["metrics"].items():
        if not all(spec.get(k) for k in ("label", "unit", "definition", "aggregation")) or spec.get(
            "direction"
        ) not in ("min", "max"):
            raise FlowError(
                f"Metric {name}: label/unit/definition/aggregation/direction are required"
            )
    records = current_runs(root)
    return {
        "definitions": definitions,
        "runs": [
            {
                "id": r["id"],
                "status": r["status"],
                "attempt": r.get("attempt"),
                "fingerprint": r.get("fingerprint"),
                "artifacts": r.get("artifacts"),
                "result_data": r.get("result_data"),
            }
            for r in records
        ],
    }


def table_data(ctx):
    definitions = ctx["definitions"]["metrics"]
    rows = []
    for record in ctx["runs"]:
        row = {
            "experiment": record["id"],
            "status": record["status"],
            "attempt": record.get("attempt", ""),
        }
        if record["status"] == "success":
            metrics = record["result_data"]["metrics"]
            if set(metrics) != set(definitions):
                raise FlowError(f"{record['id']}: metrics do not match declared definitions")
            row.update(metrics)
        rows.append(row)
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=["experiment", "status", "attempt", *definitions])
    writer.writeheader()
    writer.writerows(rows)
    return rows, stream.getvalue()


def compare(root):
    require_mutable(root)
    ctx = context(root)
    rows, csv_text = table_data(ctx)
    table = local(root, "evidence/comparison.csv")
    write_text(table, csv_text)
    value = {
        "schema_version": 1,
        "context_id": identity(ctx),
        "context": ctx,
        "rows": rows,
        "table_sha256": digest(table),
        "complete": all(r["status"] == "success" for r in rows),
    }
    write_json(local(root, "evidence/comparison.json"), value)
    journal(root, "compare", {"complete": value["complete"], "context_id": value["context_id"]})
    return value


def evidence_current(root):
    path = local(root, "evidence/comparison.json")
    if not path.exists():
        return False
    try:
        previous = read_json(path)
        ctx = context(root)
        rows, csv_text = table_data(ctx)
        return (
            previous.get("complete") is True
            and previous["context_id"] == identity(ctx)
            and previous["context"] == ctx
            and previous["rows"] == rows
            and previous["table_sha256"] == digest_bytes(csv_text.encode("utf-8"))
            and digest(local(root, "evidence/comparison.csv")) == previous["table_sha256"]
        )
    except (FlowError, OSError, KeyError):
        return False


def require_evidence(root):
    if not evidence_current(root):
        raise FlowError("Evidence is incomplete or stale; run experiments and compare again")
    return read_json(local(root, "evidence/comparison.json"))
