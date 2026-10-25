
import tempfile
import unittest
from pathlib import Path
from lab_demo.features import (
    transfer_file, beacon_schedule, simulate_persistence, simulate_self_removal
)

class LabDemoTests(unittest.TestCase):
    def test_transfer_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d)/"a", Path(d)/"b"
            a.mkdir(); b.mkdir()
            (a/"sample.txt").write_text("hello")
            result = transfer_file(a,b,"sample.txt")
            self.assertEqual(result["bytes"],5)
            self.assertEqual((b/"sample.txt").read_text(),"hello")
            self.assertRaises(ValueError,transfer_file,a,b,"../secret")

    def test_beacon(self):
        times = beacon_schedule(10,2,8)
        self.assertEqual(len(times),8)
        self.assertTrue(all(8 <= x-y <= 12 for x,y in zip(times,[0]+times[:-1])))
        self.assertRaises(ValueError,beacon_schedule,1,9,4)

    def test_lifecycle(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root/"keep.txt").write_text("safe")
            simulate_persistence(root)
            self.assertEqual(simulate_self_removal(root),["lab_lifecycle.json"])
            self.assertTrue((root/"keep.txt").exists())
            self.assertRaises(ValueError,simulate_self_removal,root)
