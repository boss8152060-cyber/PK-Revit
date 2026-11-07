# -*- coding: utf-8 -*-
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "..", "lib"))
from revotech import selecttool as st  # noqa: E402


class Decide(unittest.TestCase):
    def test_modes(self):
        self.assertEqual(st.decide(3, 0), st.MODE_BARS)
        self.assertEqual(st.decide(0, 5), st.MODE_HOSTS)
        self.assertEqual(st.decide(0, 0), st.ASK_WAY)
        self.assertEqual(st.decide(1, 1), st.ASK_MIXED)


if __name__ == "__main__":
    unittest.main()
