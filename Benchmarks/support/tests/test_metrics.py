import unittest
from unittest.mock import patch
import psutil
from Benchmarks.support.metrics import MemorySeries, ProcessMeter, paired_order


class MetricTests(unittest.TestCase):
    def test_process_identity_cpu_and_sampled_memory_scope(self):
        series = MemorySeries()
        series.add({(1, 10): {"rss": 100, "cpu": 2}, (2, 20): {"rss": 40, "cpu": 1}})
        series.add({(1, 10): {"rss": 120, "cpu": 3}})
        series.add({(1, 10): {"rss": 110, "cpu": 4}, (2, 30): {"rss": 50, "cpu": 0.5}})
        values = series.result()
        self.assertEqual(values["idle_rss_bytes"], 140)
        self.assertEqual(values["sampled_peak_rss_bytes"], 160)
        self.assertEqual(values["rss_increase_bytes"], 20)
        self.assertEqual(values["cpu_seconds"], 2.5)
        self.assertEqual(paired_order(["A", "B"], 0), ["A", "B"])
        self.assertEqual(paired_order(["A", "B"], 1), ["B", "A"])

    def test_unavailable_process_metrics_remain_missing(self):
        import psutil
        from unittest.mock import patch
        with patch("Benchmarks.support.metrics.psutil.Process", side_effect=psutil.AccessDenied(123)):
            values = ProcessMeter(123).finish()
        self.assertIsNone(values["sampled_peak_rss_bytes"])
        self.assertGreater(values["sampling_errors"], 0)
