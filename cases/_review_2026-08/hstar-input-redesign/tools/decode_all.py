#!/usr/bin/env python3
"""Decode every case with the ABI-driven decoder and report real coverage.

Replaces the thin-environment estimate in coverage.py: here the environment is
built from the deck's own values as decoding proceeds, so guards that depend on
what the file says become decidable.
"""
import json, sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from decoder import Cursor, decode, DECK_FILE, CASES

ast = json.load(open(ROOT / "data" / "deck-ast.json"))
tree = ast["trees"][ast["driver"]]
abi = json.load(open(ROOT / "data" / "deck-abi.json"))["deck_abi"]
total = {(r["file"], r["line"]) for r in abi}
deck_of = {(r["file"], r["line"]): r["deck"] for r in abi}
by_deck_total = Counter(deck_of.values())

covered, rows, stops = set(), [], Counter()
for d in sorted(CASES.glob("train*")):
    if not (d / "1.glb").exists():
        continue
    cur = {k: Cursor(path=d / v) for k, v in DECK_FILE.items() if (d / v).exists()}
    env, trace, stop, used = {}, [], [], []
    try:
        decode(tree, cur, env, trace, stop, assumed=used)
    except Exception as exc:                                   # noqa: BLE001
        stop = [{"why": f"{type(exc).__name__}: {exc}", "at": "?"}]
    cells = {(t["at"].split(":")[0], int(t["at"].split(":")[1])) for t in trace}
    new = len((cells & total) - covered)
    covered |= (cells & total)
    why = stop[0]["why"].split(":")[0] if stop else "完整走完"
    stops[why] += 1
    eof = sum(1 for c in cur.values() if c.at_eof())
    rows.append((d.name, len(trace), new, why, stop[0]["at"] if stop else "-",
                 f"{eof}/{len(cur)}"))

print(f"{'case':<30}{'解码':>6}{'新增':>6} {'读尽':>6}  停止原因")
for n, t, new, why, at, eof in rows:
    print(f"{n:<30}{t:>6}{new:>6} {eof:>6}  {why[:30]:<30} {at}")

print(f"\nDeck ABI 记录位置 {len(total)} 个，解码器确定覆盖 {len(covered)} 个 "
      f"({100*len(covered)/len(total):.1f}%)")
cov = Counter(deck_of[c] for c in covered)
for dk, n in by_deck_total.most_common():
    print(f"   {dk:<6} {cov.get(dk,0):4d} / {n:4d}   {100*cov.get(dk,0)/n:5.1f}%")
print("\n停止原因分布:")
for w, n in stops.most_common():
    print(f"   {n:3d} × {w}")
