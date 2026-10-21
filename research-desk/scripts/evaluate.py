"""Explicit CLI: no final model calls without a reviewed freeze."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import corpus, evaluation, store

parser = argparse.ArgumentParser()
commands = parser.add_subparsers(dest="command", required=True)
commands.add_parser("check")
f = commands.add_parser("freeze")
f.add_argument("--reviewed", action="store_true")
r = commands.add_parser("run")
r.add_argument("--split", choices=["validation", "final"], default="validation")
r.add_argument("--freeze-id")
args = parser.parse_args()
store.initialize()
if args.command == "check":
    output = corpus.integrity()
elif args.command == "freeze":
    output = evaluation.freeze(args.reviewed)
else:
    output = evaluation.replay(
        args.split, args.freeze_id, lambda stage, text: print(text, flush=True)
    )
print(json.dumps(output, indent=2))
