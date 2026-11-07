# -*- coding: utf-8 -*-
"""รัน test_*.py ทุกตัวใน src/PKRevit.extension (แต่ละตัวเป็น subprocess ในโฟลเดอร์ของมันเอง)
ใช้: python tools/run_all_tests.py   — คืน exit code 1 ถ้ามีตัวไหนไม่ผ่าน"""
import os
import subprocess
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src", "PKRevit.extension")
bad = []
n = 0
for d, _dirs, files in os.walk(ROOT):
    for f in sorted(files):
        if f.startswith("test_") and f.endswith(".py"):
            n += 1
            r = subprocess.run([sys.executable, f], cwd=d, capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
            tail = (r.stderr or r.stdout).strip().splitlines()[-1:] or [""]
            print(("PASS " if r.returncode == 0 else "FAIL ") + f + "  " + tail[0])
            if r.returncode:
                bad.append((f, r.stderr[-1500:]))
for f, e in bad:
    print("\n==== " + f + "\n" + e)
print("\n%d files, %d failed" % (n, len(bad)))
sys.exit(1 if bad else 0)
