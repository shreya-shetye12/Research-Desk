"""Run or report the explicit Research Desk development comparison."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend import benchmark

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["run", "report"])
    parser.add_argument("--out", type=Path, default=ROOT / "results/evaluation.json")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if args.command == "run":
        benchmark.run(args.out, args.resume)
    print(json.dumps(benchmark.report(args.out), indent=2))
