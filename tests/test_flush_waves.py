import unittest
from aquaflow.api import AquaFlowService
from aquaflow.flush.plan import Hydrant, waves
from aquaflow.workflow_rules import evaluate


def h(id, flow, sensitive=False):
    return Hydrant(id, flow, sensitive)


def wave_flows(result, rows):
    by_id = {r.id: r.flow for r in rows}
    return [sum(by_id[i] for i in wave) for wave in result]


class FlushWaveDomainTest(unittest.TestCase):
    def test_wave_fills_exactly_to_limit(self):
        rows = [h("A", 5), h("B", 5), h("C", 5), h("D", 5)]
        result = waves(rows, 10, 2)
        self.assertEqual(result, [["A", "B"], ["C", "D"]])
        self.assertTrue(all(len(wave) == 2 for wave in result))
        self.assertTrue(all(f >= 10 for f in wave_flows(result, rows)))

    def test_candidates_exceeding_limit_spill_to_next_wave(self):
        rows = [h(c, 4) for c in "ABCDEF"]
        result = waves(rows, 8, 2)
        self.assertEqual(result, [["A", "B"], ["C", "D"], ["E", "F"]])
        self.assertTrue(all(len(wave) <= 2 for wave in result))
        self.assertTrue(all(f >= 8 for f in wave_flows(result, rows)))

    def test_limit_is_hard_when_reaching_flow_would_overflow(self):
        # Top-2 hydrants only deliver 8 < 10; the third must not be
        # swept into the same wave to close the gap.
        rows = [h("A", 4), h("B", 4), h("C", 4)]
        with self.assertRaises(ValueError):
            waves(rows, 10, 2)

    def test_insufficient_total_flow_raises(self):
        with self.assertRaises(ValueError):
            waves([h("A", 3), h("B", 3)], 10, 5)

    def test_sensitive_hydrant_scheduled_alone(self):
        rows = [h("A", 6), h("B", 6), h("S", 10, sensitive=True)]
        result = waves(rows, 10, 4)
        self.assertEqual(result, [["A", "B"], ["S"]])

    def test_sensitive_hydrants_each_get_own_wave(self):
        rows = [h("S2", 10, sensitive=True), h("S1", 10, sensitive=True)]
        self.assertEqual(waves(rows, 10, 4), [["S1"], ["S2"]])

    def test_sensitive_hydrant_below_required_flow_raises(self):
        # A sensitive hydrant cannot piggyback on a shared wave, so its
        # own flow must independently meet the requirement.
        rows = [h("A", 10), h("S", 4, sensitive=True)]
        with self.assertRaises(ValueError):
            waves(rows, 10, 4)


class FlushWaveWorkflowTest(unittest.TestCase):
    def payload(self, flows, required, max_parallel):
        return {
            "hydrants": [
                {"id": i, "flow": f, "sensitive": s} for i, f, s in flows
            ],
            "required": required,
            "max_parallel": max_parallel,
        }

    def test_workflow_enforces_hard_limit(self):
        flows = [("A", 6, False), ("B", 6, False), ("C", 6, False), ("D", 6, False)]
        result = AquaFlowService().run_workflow("flush_waves", self.payload(flows, 10, 2))
        self.assertEqual(result["decision"], "execute")
        self.assertEqual(result["value"], [["A", "B"], ["C", "D"]])
        self.assertEqual(result["evidence"], {"wave_count": 2})
        self.assertTrue(all(len(wave) <= 2 for wave in result["value"]))

    def test_workflow_limit_is_hard_without_transport_annotation(self):
        # evaluate() must enforce the configured limit even when the
        # payload never passed through normalize().
        flows = [("A", 4, False), ("B", 4, False), ("C", 4, False)]
        with self.assertRaises(ValueError):
            evaluate("flush_waves", self.payload(flows, 10, 2))

    def test_workflow_propagates_insufficient_error(self):
        flows = [("A", 4, False), ("B", 4, False), ("C", 4, False)]
        with self.assertRaises(ValueError):
            AquaFlowService().run_workflow("flush_waves", self.payload(flows, 10, 2))

    def test_workflow_sensitive_hydrant_alone(self):
        flows = [("A", 6, False), ("B", 6, False), ("S", 10, True)]
        result = AquaFlowService().run_workflow("flush_waves", self.payload(flows, 10, 4))
        self.assertEqual(result["value"], [["A", "B"], ["S"]])


if __name__ == "__main__":
    unittest.main()
