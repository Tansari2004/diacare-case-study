import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('workflow', Path(__file__).parents[1] / 'evaluate.py')
workflow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(workflow)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        # Bytes test identity accounting only; these are not actual photo results.
        for i in range(3):
            (self.root / f'{i}.bin').write_bytes(f'fabricated fixture {i}'.encode())
        cases = []
        for i in range(3):
            cases.append({'id': str(i), 'image': f'{i}.bin', 'permission': 'fabricated test bytes',
                          'source_identifier': f'test:{i}', 'label_reviewer': 'fixture, not independent review',
                          'groups': ['regional_food'] if i < 2 else ['nonfood'],
                          'expected_status': 'food' if i < 2 else 'nonfood',
                          'accepted_entries': [{'catalogue_id': 'rice', 'unit': 'g', 'min_quantity': 90, 'max_quantity': 110}] if i < 2 else []})
        (self.root / 'manifest.json').write_text(json.dumps({'cases': cases, 'catalogue_sha256': 'a' * 64}))
        (self.root / 'development.json').write_text('[]')
        self.reservation = self.root / 'reservation.json'
        workflow.freeze(self.root / 'manifest.json', self.root / 'development.json', self.reservation)
        rows = []
        for i in range(3):
            rows.append({'id': str(i), 'image_sha256': workflow.digest(self.root / f'{i}.bin'),
                         'status': 'saved' if i == 0 else 'failed' if i == 1 else 'rejected_nonfood',
                         'confirmed_entry': {'catalogue_id': 'rice', 'unit': 'g', 'quantity': 100} if i == 0 else None,
                         'corrections': 1 if i == 0 else 0, 'raw_prediction': {'fixture': True},
                         'trace_identifier': f'fixture:{i}', 'upload_ms': 10, 'inference_ms': 20,
                         'request_ms': 40, 'workflow_ms': 100})
        self.run = {'provider': 'fixture', 'model_version': 'fixture-v1', 'client_version': 'fixture-v1',
                    'device': 'test harness', 'run_id': 'fabricated-fixture', 'startup_ms': 1000,
                    'evidence_status': 'fabricated_unit_test_only', 'catalogue_sha256': 'a' * 64,
                    'reservation_sha256': workflow.digest(self.reservation), 'cases': rows}

    def score(self):
        trace = self.root / 'traces.json'
        trace.write_text(json.dumps(self.run))
        return workflow.evaluate(self.reservation, trace)

    def test_failures_count_as_misses_with_stage_timings(self):
        report = self.score()
        self.assertEqual(report['food_cases'], 2)
        self.assertEqual(report['confirmed_item_and_serving_success_rate'], .5)
        self.assertEqual(report['nonfood_correct_rejection_rate'], 1)
        self.assertEqual(report['failures'], 1)
        self.assertEqual(report['startup_ms'], 1000)
        self.assertEqual(report['timings_ms_including_failures']['request_ms']['mean'], 40)

    def test_wrong_serving_or_item_is_not_a_success(self):
        self.run['cases'][0]['confirmed_entry']['quantity'] = 200
        self.assertEqual(self.score()['confirmed_item_and_serving_success_rate'], 0)
        self.run['cases'][0]['confirmed_entry']['quantity'] = 100
        self.run['cases'][0]['confirmed_entry']['catalogue_id'] = 'bread'
        self.assertEqual(self.score()['confirmed_item_and_serving_success_rate'], 0)

    def test_nonfood_saved_is_a_failure(self):
        self.run['cases'][2]['status'] = 'saved'
        self.run['cases'][2]['confirmed_entry'] = {'catalogue_id': 'rice', 'unit': 'g', 'quantity': 100}
        self.assertEqual(self.score()['nonfood_incorrectly_saved'], 1)
        self.assertEqual(self.score()['nonfood_correct_rejection_rate'], 0)

    def test_missing_cases_cannot_inflate_results(self):
        self.run['cases'].pop(1)
        with self.assertRaises(ValueError): self.score()

    def test_changed_image_catalogue_or_reservation_fails(self):
        for field in ['catalogue_sha256', 'reservation_sha256']:
            old = self.run[field]
            self.run[field] = 'b' * 64
            with self.assertRaises(ValueError): self.score()
            self.run[field] = old
        self.run['cases'][0]['image_sha256'] = 'c' * 64
        with self.assertRaises(ValueError): self.score()

    def test_invalid_timing_fails(self):
        self.run['cases'][0]['inference_ms'] = 1000
        with self.assertRaises(ValueError): self.score()
        self.run['cases'][0]['inference_ms'] = float('nan')
        with self.assertRaises(ValueError): self.score()

    def test_development_duplicates_cannot_be_reserved(self):
        (self.root / 'development.json').write_text(json.dumps([workflow.digest(self.root / '0.bin')]))
        with self.assertRaises(ValueError):
            workflow.freeze(self.root / 'manifest.json', self.root / 'development.json', self.root / 'bad.json')

    def test_comparison_requires_identical_reserved_tasks(self):
        a = self.root / 'a.json'; b = self.root / 'b.json'
        report = self.score()
        a.write_text(json.dumps(report))
        report['provider'] = 'second fixture'
        b.write_text(json.dumps(report))
        self.assertEqual(len(workflow.compare([a, b])['providers']), 2)
        report['reservation_sha256'] = 'd' * 64
        b.write_text(json.dumps(report))
        with self.assertRaises(ValueError): workflow.compare([a, b])

    def test_reservation_does_not_overwrite(self):
        with self.assertRaises(FileExistsError):
            workflow.freeze(self.root / 'manifest.json', self.root / 'development.json', self.reservation)


if __name__ == '__main__': unittest.main()
