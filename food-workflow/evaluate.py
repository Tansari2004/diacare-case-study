"""Offline audit of reserved photo-workflow traces; does not run an app/model.

All example traces are fabricated test fixtures. Real evaluation requires
permitted fresh photos, independently reviewed labels and actual device traces.
"""
import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean


GROUPS = {"regional_food", "mixed_plate", "unfamiliar_dish", "poor_lighting", "nonfood"}


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while block := stream.read(1024 * 1024):
            h.update(block)
    return h.hexdigest()


def load(path):
    return json.loads(Path(path).read_text())


def save_new(path, content):
    with Path(path).open("x") as stream:
        json.dump(content, stream, indent=2, allow_nan=False)
        stream.write("\n")


def freeze(manifest_path, development_index, output):
    manifest = load(manifest_path)
    development = load(development_index)
    if not isinstance(development, list) or not all(isinstance(v, str) and len(v) == 64 for v in development):
        raise ValueError("Development index must list image SHA-256 values")
    cases = manifest["cases"]
    if not cases or len({row["id"] for row in cases}) != len(cases):
        raise ValueError("Cases must be nonempty with unique IDs")
    seen = set()
    for row in cases:
        if not row.get("permission") or not row.get("source_identifier") or not row.get("label_reviewer"):
            raise ValueError("Each case needs permission, permitted source ID and label reviewer")
        if not row.get("groups") or not set(row["groups"]) <= GROUPS:
            raise ValueError("Unknown or missing evaluation groups")
        if row["expected_status"] not in {"food", "nonfood"}:
            raise ValueError("Expected status must be food or nonfood")
        if row["expected_status"] == "food":
            if not row.get("accepted_entries"):
                raise ValueError("Food cases need accepted catalogue/serving labels")
            for entry in row["accepted_entries"]:
                if not entry.get("catalogue_id") or not entry.get("unit") or not 0 < entry["min_quantity"] <= entry["max_quantity"]:
                    raise ValueError("Invalid accepted serving")
        elif row.get("accepted_entries"):
            raise ValueError("Nonfood cases cannot have accepted food entries")
        image_hash = digest(Path(manifest_path).parent / row["image"])
        if image_hash in seen or image_hash in development:
            raise ValueError("Duplicate or development image in reserved set")
        seen.add(image_hash)
        row["image_sha256"] = image_hash
        # Private paths are not needed in public scoring artifacts.
        row.pop("image")
    reservation = {"format": "food-workflow-reservation-v1", "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
                   "manifest_sha256": digest(manifest_path), "development_index_sha256": digest(development_index),
                   "catalogue_sha256": manifest["catalogue_sha256"], "cases": cases,
                   "independence_note": "Exact hash checks only; human review must establish freshness, semantic independence and label quality"}
    save_new(output, reservation)
    return reservation


def valid_ms(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def evaluate(reservation_path, traces_path):
    reservation, run = load(reservation_path), load(traces_path)
    if run["reservation_sha256"] != digest(reservation_path):
        raise ValueError("Trace run does not match frozen reservation")
    if run["catalogue_sha256"] != reservation["catalogue_sha256"]:
        raise ValueError("Catalogue version differs from the accepted labels")
    if not all(run.get(k) for k in ("provider", "model_version", "client_version", "device", "run_id")):
        raise ValueError("Record provider/model/client/device/run versions")
    if not valid_ms(run["startup_ms"]):
        raise ValueError("Record actual process/model startup time separately")
    rows = run["cases"]
    expected = {case["id"]: case for case in reservation["cases"]}
    if len(rows) != len(expected) or {row["id"] for row in rows} != set(expected):
        raise ValueError("Every reserved case must have exactly one result, including failures")
    results = []
    for row in rows:
        case = expected[row["id"]]
        if row["image_sha256"] != case["image_sha256"]:
            raise ValueError("Image identity changed")
        for timing in ("upload_ms", "inference_ms", "request_ms", "workflow_ms"):
            if not valid_ms(row[timing]):
                raise ValueError("Record finite nonnegative stage timings, including timeouts")
        if row["upload_ms"] + row["inference_ms"] > row["request_ms"] + 1 or row["workflow_ms"] < row["request_ms"]:
            raise ValueError("Stage timing boundaries are inconsistent")
        if not isinstance(row["corrections"], int) or row["corrections"] < 0:
            raise ValueError("Record nonnegative user correction count")
        if not isinstance(row["raw_prediction"], dict) or not row.get("trace_identifier"):
            raise ValueError("Preserve individual prediction and trace identifier")
        if row["status"] not in {"saved", "rejected_nonfood", "failed", "abandoned"}:
            raise ValueError("Unknown workflow outcome")
        confirmed = row.get("confirmed_entry")
        success = False
        if case["expected_status"] == "nonfood":
            success = row["status"] == "rejected_nonfood" and confirmed is None
        elif row["status"] == "saved" and confirmed:
            success = any(confirmed["catalogue_id"] == entry["catalogue_id"] and confirmed["unit"] == entry["unit"]
                          and valid_ms(confirmed["quantity"]) and entry["min_quantity"] <= confirmed["quantity"] <= entry["max_quantity"]
                          for entry in case["accepted_entries"])
        results.append({**row, "expected_status": case["expected_status"], "groups": case["groups"], "success": success})
    foods = [r for r in results if r["expected_status"] == "food"]
    nonfoods = [r for r in results if r["expected_status"] == "nonfood"]
    def rate(items):
        return sum(r["success"] for r in items) / len(items) if items else None
    def timing_summary(field):
        values = sorted(r[field] for r in results)
        return {"mean": mean(values), "p95": values[math.ceil(.95 * len(values)) - 1]}
    return {"evidence_status": run.get("evidence_status", "unverified_recorded_traces"),
            "reservation_sha256": digest(reservation_path), "traces_sha256": digest(traces_path),
            "provider": run["provider"], "model_version": run["model_version"],
            "catalogue_sha256": run["catalogue_sha256"], "cases": len(results),
            "food_cases": len(foods), "confirmed_item_and_serving_success_rate": rate(foods),
            "nonfood_cases": len(nonfoods), "nonfood_correct_rejection_rate": rate(nonfoods),
            "nonfood_incorrectly_saved": sum(r["status"] == "saved" for r in nonfoods),
            "failures": sum(r["status"] == "failed" for r in results),
            "abandoned": sum(r["status"] == "abandoned" for r in results),
            "mean_corrections_all_cases": mean(r["corrections"] for r in results),
            "startup_ms": run["startup_ms"],
            "timings_ms_including_failures": {field: timing_summary(field) for field in ("upload_ms", "inference_ms", "request_ms", "workflow_ms")},
            "groups": {group: {"cases": len(subset), "success_rate": rate(subset)} for group in sorted(GROUPS)
                       if (subset := [r for r in results if group in r["groups"]])},
            "case_results": results}


def compare(report_paths):
    reports = [load(path) for path in report_paths]
    if len(reports) < 2:
        raise ValueError("Provide at least two provider reports")
    reference = reports[0]
    for report in reports[1:]:
        for key in ("reservation_sha256", "catalogue_sha256"):
            if report[key] != reference[key]:
                raise ValueError("Providers must use identical reserved cases and accepted catalogue/serving definitions")
    return {"comparison": "Confirmed item+serving for food; no saved entry and correct rejection for nonfood",
            "reservation_sha256": reference["reservation_sha256"],
            "providers": [{k: report[k] for k in ("provider", "model_version", "cases", "confirmed_item_and_serving_success_rate", "nonfood_correct_rejection_rate", "failures")}
                          for report in reports]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    reserve = commands.add_parser("freeze")
    reserve.add_argument("manifest", type=Path)
    reserve.add_argument("development_index", type=Path)
    reserve.add_argument("output", type=Path)
    score = commands.add_parser("evaluate")
    score.add_argument("reservation", type=Path)
    score.add_argument("traces", type=Path)
    score.add_argument("output", type=Path)
    comparison = commands.add_parser("compare")
    comparison.add_argument("reports", type=Path, nargs="+")
    args = parser.parse_args()
    if args.command == "freeze":
        freeze(args.manifest, args.development_index, args.output)
        print("Reserved image identities and accepted labels. Human independence review remains required.")
    elif args.command == "evaluate":
        save_new(args.output, evaluate(args.reservation, args.traces))
        print(args.output)
    else:
        print(json.dumps(compare(args.reports), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
