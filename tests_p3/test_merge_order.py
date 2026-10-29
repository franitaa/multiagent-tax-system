"""MEM-6: aggregation is independent of worker completion order."""
import itertools
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from silverfile_extraction.memory import merge_versioned

class MergeOrderTests(unittest.TestCase):
    def test_permutations_and_replay(self):
        updates = [{'a': {'revision': 1}}, {'b': {'revision': 1}}, {'a': {'revision': 2}}]
        for order in itertools.permutations(updates):
            result = {}
            for update in order:
                result = merge_versioned(result, update)
            self.assertEqual(result, {'a': {'revision': 2}, 'b': {'revision': 1}})
            self.assertEqual(merge_versioned(result, result), result)

    def test_parallel_worker_results_all_survive(self):
        result = {}
        with ThreadPoolExecutor(max_workers=4) as executor:
            pending = [executor.submit(lambda i=i: {str(i): {'revision': 1}}) for i in range(20)]
            for future in as_completed(pending):
                result = merge_versioned(result, future.result())
        self.assertEqual(len(result), 20)
