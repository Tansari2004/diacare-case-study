# Food AI: reserved workflow evaluation kit

**Status: instrumentation and offline trace scoring, not completed model or user evaluation.** No fresh photos, independent labels, production traces or new performance claims are included. Tests use fabricated bytes/outcomes only. This public kit contains no production app code or patient information.

The historical food-name ranking experiment remains unchanged. It bypassed the food gate and cannot establish photo-to-confirmed-entry success. This kit adds a common task definition and provenance/accounting checks for a future complete-path evaluation.

## Before tuning again

Reserve permitted, fresh photos and independently reviewed labels. Include regional foods, mixed plates, unfamiliar dishes, poor lighting, and nonfood. Record source identifiers and permission; keep private images out of Git. Check against every development image hash and have a person review near-duplicates and reused meal/session families. Exact hashes alone cannot prove independence. Set the final sample size and acceptable performance/uncertainty before viewing predictions.

For each case, specify accepted **catalogue IDs, serving units and quantity ranges**. Accepted entries are alternatives for one intended saved entry, not a list of all ingredients. For a mixed plate, define the intended whole-dish catalogue entry or a specific declared item; this version does not score the completeness of multiple separately saved components. Review serving ranges with an appropriate reviewer; do not infer them from an uncalibrated photo.

Manifest structure (paths are private and relative to the manifest):

```json
{
  "catalogue_sha256": "SHA256_OF_FROZEN_CATALOGUE",
  "cases": [{
    "id": "fresh-001",
    "image": "private/001.jpg",
    "source_identifier": "PERMITTED_IMAGE_IDENTIFIER",
    "permission": "DOCUMENTED_PERMISSION",
    "label_reviewer": "ACTUAL_REVIEWER",
    "groups": ["regional_food", "poor_lighting"],
    "expected_status": "food",
    "accepted_entries": [{"catalogue_id": "CATALOGUE_ID", "unit": "g", "min_quantity": 90, "max_quantity": 110}]
  }]
}
```

Nonfood cases use `expected_status: "nonfood"`, group `nonfood`, and an empty `accepted_entries` list. `development.json` lists SHA-256 values for all previously used images. Do not use an empty list to claim independence if development assets exist.

```bash
python food-workflow/evaluate.py freeze manifest.json development.json reservation.json
```

This writes a new reservation, recording image/manifest/catalogue hashes, labels and timestamp, and refuses to overwrite it. Do not amend labels after seeing outputs; archive an error correction and treat any examined set as development evidence when choosing improvements.

## Capture actual workflow traces

Run each provider against exactly the same frozen tasks and catalogue version. Capture the real food gate, catalogue selection, editable serving confirmation and successful save, including errors and abandoned attempts. The kit does **not** automatically operate a phone, call a provider or verify a database save; the trace must come from instrumented client/server events plus the confirmed saved record. A manually entered trace needs its own audit against those records.

Run fields: `run_id`, `provider`, immutable `model_version`/revision, `client_version`, `device`, `catalogue_sha256`, `reservation_sha256`, separately measured `startup_ms`, `evidence_status`, and `cases`.

Each case: `id`, `image_sha256`, `trace_identifier`, individual `raw_prediction` (gate result and returned catalogue candidates/ingredient names), `status` (`saved`, `rejected_nonfood`, `failed`, `abandoned`), `confirmed_entry` or null, user `corrections`, and `upload_ms`, `inference_ms`, `request_ms`, `workflow_ms`. A confirmed entry has `catalogue_id`, `unit`, `quantity`.

Measure startup from process start to ready once per run. Measure upload and inference using aligned boundaries; `request_ms` runs from request start to suggestions/error and must include both. `workflow_ms` continues through confirmation/save or failure/abandonment. Human correction time belongs in workflow time, not inference. Include timeouts and failures with their actual elapsed time. Preserve raw output separately from the edited confirmed entry. Keep sensitive traces in approved private storage.

```bash
python food-workflow/evaluate.py evaluate reservation.json provider-a-traces.json provider-a-report.json
python food-workflow/evaluate.py evaluate reservation.json provider-b-traces.json provider-b-report.json
python food-workflow/evaluate.py compare provider-a-report.json provider-b-report.json
python -m unittest discover -s food-workflow/tests -v
```

Food success requires the accepted catalogue item **and serving** to have been saved. Nonfood success requires correct rejection with no saved entry. Missing results fail validation; request failures and abandonments remain in denominators. Reports preserve row-level outputs, group rates, corrections, startup and per-stage mean/p95 timings including failures. A small group count is not reliable coverage evidence; report counts and uncertainty when collecting a real set.

All providers use this same confirmed-entry task, even if their raw outputs differ. A catalogue adapter and user confirmation are necessary for an open-ended naming provider. Name-ranking recall and open-ended ingredient recall must not be compared as identical outputs.

For a speed claim, reserve the same hardware, input set, network conditions, warm/cold regime and number/order of repeats before comparison. Report startup, upload, inference, request and workflow time separately. This scorer checks trace consistency; it does not establish controlled timing or a speed improvement by itself.

## Still required

A fresh independently labeled reservation; actual model/app/device traces; verified saved-record evidence; provider/model/catalogue versions; independent label review; and a controlled performance run. No new accuracy, latency, usability or health benefit is claimed until that evidence exists.
