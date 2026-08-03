#!/bin/bash
# Convenience script to run concurrency tests with various options

set -e

echo "================================================"
echo "  Tale-AI Concurrency Lock Tests (Issue #130)"
echo "================================================"
echo ""

# Check if pytest is available
if ! command -v pytest &> /dev/null; then
    echo "❌ pytest not found. Please install: pip install pytest pytest-asyncio"
    exit 1
fi

echo "✓ pytest found"
echo ""

# Function to run tests with specific options
run_test() {
    local name=$1
    local cmd=$2

    echo "──────────────────────────────────────────────"
    echo "Running: $name"
    echo "──────────────────────────────────────────────"
    eval $cmd
    echo ""
}

# Default: Run all tests with verbose output
if [ $# -eq 0 ]; then
    echo "Running all concurrency tests..."
    echo ""
    run_test "All Tests" "pytest tests/unit/test_concurrency_lock.py -v"
    exit 0
fi

# Parse command line arguments
case "$1" in
    "all")
        run_test "All Tests (Verbose)" "pytest tests/unit/test_concurrency_lock.py -v -s"
        ;;
    "parallel")
        run_test "Parallel Sessions Test" "pytest tests/unit/test_concurrency_lock.py::test_parallel_different_sessions -v -s"
        ;;
    "serial")
        run_test "Serial Same Session Test" "pytest tests/unit/test_concurrency_lock.py::test_serial_same_session -v -s"
        ;;
    "semaphore")
        run_test "Semaphore Limit Test" "pytest tests/unit/test_concurrency_lock.py::test_semaphore_limit -v -s"
        ;;
    "stateless")
        run_test "ChatLLM Stateless Test" "pytest tests/unit/test_concurrency_lock.py::test_chatllm_stateless -v -s"
        ;;
    "stress")
        run_test "High Concurrency Stability Test" "pytest tests/unit/test_concurrency_lock.py::test_high_concurrency_stability -v -s"
        ;;
    "locks")
        run_test "Lock Acquisition Order Test" "pytest tests/unit/test_concurrency_lock.py::test_lock_acquisition_order -v -s"
        ;;
    "quick")
        echo "Running quick validation (no output capture)..."
        pytest tests/unit/test_concurrency_lock.py --tb=short
        ;;
    "report")
        echo "Generating HTML report..."
        pytest tests/unit/test_concurrency_lock.py --html=concurrency_test_report.html --self-contained-html
        echo "✓ Report generated: concurrency_test_report.html"
        ;;
    "help"|"-h"|"--help")
        echo "Usage: $0 [option]"
        echo ""
        echo "Options:"
        echo "  (none)      Run all tests with standard output"
        echo "  all         Run all tests with detailed output"
        echo "  parallel    Test parallel execution for different sessions"
        echo "  serial      Test serial execution for same session"
        echo "  semaphore   Test semaphore concurrency limit"
        echo "  stateless   Test ChatLLM stateless behavior"
        echo "  stress      Test high concurrency stability"
        echo "  locks       Test lock acquisition order"
        echo "  quick       Quick validation with minimal output"
        echo "  report      Generate HTML test report"
        echo "  help        Show this help message"
        echo ""
        echo "Examples:"
        echo "  $0                  # Run all tests"
        echo "  $0 parallel         # Run only parallel test"
        echo "  $0 report           # Generate HTML report"
        ;;
    *)
        echo "❌ Unknown option: $1"
        echo "Run '$0 help' for usage information"
        exit 1
        ;;
esac

echo "================================================"
echo "  Test execution complete"
echo "================================================"
