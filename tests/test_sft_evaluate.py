import json
from pathlib import Path
import tempfile
import unittest

from sciquarry.sft_evaluate import compare


class SFTComparisonTests(unittest.TestCase):
    def test_comparison_requires_matching_inputs_and_base_then_adapter(self):
        with tempfile.TemporaryDirectory() as tmp:
            before, after = Path(tmp) / 'before', Path(tmp) / 'after'
            metadata = {'type': 'metadata', 'data_manifest_sha256': 'dataset', 'model_files': {'a': 'b'},
                        'max_tokens': 100, 'temperature': 0, 'no_thinking': True, 'packages': {'mlx': '1'},
                        'data_kind': 'synthetic', 'adapter_sha256': None}
            result = {'type': 'result', 'sample_id': 'a', 'question': 'q', 'evidence_ids': ['SYN:1:p1'], 'answer': 'x'}
            def write(path, meta, row=result):
                path.write_text('\n'.join(json.dumps(x) for x in (meta, row, {'type': 'summary', 'count': 1})) + '\n')
            write(before, metadata)
            write(after, {**metadata, 'adapter_sha256': 'weights'})
            self.assertEqual(compare(before, after)['cases'][0]['review_status'], 'pending_human_review')
            write(after, {**metadata, 'adapter_sha256': 'weights', 'model_files': {'a': 'different'}})
            with self.assertRaisesRegex(ValueError, 'model_files'): compare(before, after)
            write(after, metadata)
            with self.assertRaisesRegex(ValueError, 'adapter'): compare(before, after)
            write(after, {**metadata, 'adapter_sha256': 'weights'}, {**result, 'evidence_ids': ['SYN:2:p1']})
            with self.assertRaisesRegex(ValueError, 'evidence'): compare(before, after)

    def test_incomplete_evaluation_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = Path(tmp) / 'a'; a.write_text('{"type":"metadata"}\n')
            with self.assertRaisesRegex(ValueError, 'incomplete'): compare(a, a)


if __name__ == '__main__': unittest.main()
