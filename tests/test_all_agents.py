import os
import sys
import subprocess

TEST_SCRIPTS = [
    "tests/test_dealforge.py",
    "tests/test_tech_diligence.py",
    "tests/test_esg_module.py",
    "tests/test_cyber_regulatory.py",
    "tests/test_integration_module.py",
    "tests/test_sector_loader.py",
    "tests/test_langgraph.py",
    "tests/test_full_integration.py",
]


def run_all_tests():
    print("=========================================")
    print("  DEALFORGE AI - MASTER TEST SUITE       ")
    print("=========================================")

    passed = 0
    failed = 0

    for script in TEST_SCRIPTS:
        print(f"\n>> Running: {script}")
        print("-" * 40)

        if not os.path.exists(script) and os.path.exists(f"../{script}"):
            script_path = f"../{script}"
        else:
            script_path = script

        if not os.path.exists(script_path):
            if script == "tests/test_dealforge.py":
                script_path = "backend/test_dealforge.py"

        if not os.path.exists(script_path):
            print(f"[SKIP] Script not found: {script_path}")
            continue

        try:
            env = os.environ.copy()
            env["PYTHONPATH"] = "backend"
            env["PYTHONIOENCODING"] = "utf-8"

            result = subprocess.run(
                [sys.executable, "-X", "utf8", script_path],
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

            if result.returncode == 0:
                print(f"[PASS] {script}")
                passed += 1
            else:
                print(f"[FAIL] {script} returned code {result.returncode}")
                lines = result.stderr.splitlines()[-15:]
                if not lines:
                    lines = result.stdout.splitlines()[-15:]
                print("\n".join(lines))
                failed += 1

        except Exception as e:
            print(f"[ERROR] Failed to run {script}: {e}")
            failed += 1

    print("\n=========================================")
    print(f"  FINAL RESULTS: {passed} PASSED / {failed} FAILED")
    print("=========================================")

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    run_all_tests()
