#!/usr/bin/env python
"""
Test runner for ChatAgent Stage 3 tests

Runs all tests and generates performance report.
"""
import subprocess
import sys
import json
from pathlib import Path


def run_tests():
    """Run all ChatAgent tests"""
    print("=" * 80)
    print("Stage 3: ChatAgent Unit Tests")
    print("=" * 80)
    print()

    test_dir = Path(__file__).parent / "unit" / "agent"

    # Test categories
    test_files = [
        ("LLMAgent Base", "test_llm_agent_base.py"),
        ("ChatAgent Basic", "test_chat_agent_basic.py"),
        ("ChatAgent Concurrency [CRITICAL]", "test_chat_agent_concurrency.py"),
        ("ChatAgent Performance [CRITICAL]", "test_chat_agent_performance.py"),
        ("ChatAgent Timeout [CRITICAL]", "test_chat_agent_timeout.py"),
        ("ChatAgent Locks", "test_chat_agent_locks.py"),
    ]

    results = {}
    all_passed = True

    for category, filename in test_files:
        print(f"\n{'=' * 80}")
        print(f"Running: {category}")
        print(f"File: {filename}")
        print(f"{'=' * 80}\n")

        test_path = test_dir / filename

        # Run pytest with verbose output
        result = subprocess.run(
            [
                sys.executable, "-m", "pytest",
                str(test_path),
                "-v",
                "-s",  # Show print output
                "--tb=short",  # Short traceback
            ],
            capture_output=True,
            text=True
        )

        # Store result
        results[category] = {
            "passed": result.returncode == 0,
            "output": result.stdout + result.stderr
        }

        print(result.stdout)
        if result.stderr:
            print(result.stderr)

        if result.returncode != 0:
            all_passed = False
            print(f"\n❌ {category} FAILED")
        else:
            print(f"\n✅ {category} PASSED")

    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)

    for category, result in results.items():
        status = "✅ PASS" if result["passed"] else "❌ FAIL"
        print(f"{status} - {category}")

    print()
    if all_passed:
        print("🎉 ALL TESTS PASSED! Ready for Stage 4.")
        return 0
    else:
        print("❌ SOME TESTS FAILED. Fix issues before proceeding.")
        return 1


def run_coverage():
    """Run tests with coverage report"""
    print("\n" + "=" * 80)
    print("Running Coverage Analysis")
    print("=" * 80 + "\n")

    result = subprocess.run(
        [
            sys.executable, "-m", "pytest",
            "tests/unit/agent/",
            "--cov=core.llm.agent",
            "--cov-report=term-missing",
            "--cov-report=html:tests/coverage_report",
        ],
        capture_output=True,
        text=True
    )

    print(result.stdout)
    if result.stderr:
        print(result.stderr)

    print("\n📊 Coverage report generated at: tests/coverage_report/index.html")


if __name__ == "__main__":
    # Run tests
    exit_code = run_tests()

    # Run coverage if all tests passed
    if exit_code == 0:
        try:
            run_coverage()
        except Exception as e:
            print(f"\n⚠️  Coverage report failed: {e}")

    sys.exit(exit_code)
