"""Runner to execute all backend test cases cleanly."""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

# Add backend to sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

import test_batch0
import test_pipeline
import test_jobs_stage_done
import test_video

test_modules = [test_batch0, test_pipeline, test_jobs_stage_done, test_video]

passed = 0
failed = 0

print("=== Running Backend Test Suite ===")

for mod in test_modules:
    for name in dir(mod):
        if name.startswith("test_"):
            fn = getattr(mod, name)
            if callable(fn):
                try:
                    fn()
                    print(f"  [PASS] {mod.__name__}.{name}")
                    passed += 1
                except Exception as exc:
                    print(f"  [FAIL] {mod.__name__}.{name}:")
                    traceback.print_exc()
                    failed += 1

print("-----------------------------------")
print(f"Total: {passed + failed} | Passed: {passed} | Failed: {failed}")

if failed > 0:
    sys.exit(1)
sys.exit(0)
