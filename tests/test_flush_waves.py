import unittest

from aquaflow.api import AquaFlowService
from aquaflow.flush.plan import Hydrant, waves


def h(id, flow, sensitive=False):
    return Hydrant(id, float(flow), sensitive)


class FlushWaveTests(unittest.TestCase):
    def test_wave_can_reach_but_not_exceed_parallel_limit(self):
        self.assertEqual(waves([h("a", 4), h("b", 4), h("c", 4)], 12, 3), [["a", "b", "c"]])

    def test_candidates_over_limit_are_split_into_independent_waves(self):
        self.assertEqual(
            waves([h("a", 3), h("b", 3), h("c", 3), h("d", 3)], 5, 2),
            [["a", "b"], ["c", "d"]],
        )

    def test_hard_limit_does_not_mask_insufficient_flow(self):
        with self.assertRaisesRegex(ValueError, "insufficient"):
            waves([h("a", 4), h("b", 4), h("c", 4)], 10, 2)

    def test_sensitive_hydrants_remain_sorted_and_are_alone(self):
        rows = [h("c", 4), h("a", 4), h("s-low", 6, True), h("s-high", 7, True)]
        self.assertEqual(waves(rows, 4, 3), [["a"], ["c"], ["s-high"], ["s-low"]])

    def test_sensitive_hydrant_cannot_borrow_flow_from_others(self):
        with self.assertRaisesRegex(ValueError, "insufficient"):
            waves([h("regular", 3), h("sensitive", 3, True)], 4, 2)

    def test_workflow_enforces_hard_parallel_limit(self):
        service = AquaFlowService()
        payload = {
            "hydrants": [
                {"id": "a", "flow": 3, "sensitive": False},
                {"id": "b", "flow": 3, "sensitive": False},
                {"id": "c", "flow": 3, "sensitive": False},
                {"id": "d", "flow": 3, "sensitive": False},
            ],
            "required": 5,
            "max_parallel": 2,
        }
        result = service.run_workflow("flush_waves", payload)
        self.assertEqual(result["value"], [["a", "b"], ["c", "d"]])
        self.assertTrue(all(len(wave) <= 2 for wave in result["value"]))

        with self.assertRaisesRegex(ValueError, "insufficient"):
            service.run_workflow(
                "flush_waves",
                {
                    "hydrants": [
                        {"id": "a", "flow": 4, "sensitive": False},
                        {"id": "b", "flow": 4, "sensitive": False},
                        {"id": "c", "flow": 4, "sensitive": False},
                    ],
                    "required": 10,
                    "max_parallel": 2,
                },
            )


if __name__ == "__main__":
    unittest.main()
