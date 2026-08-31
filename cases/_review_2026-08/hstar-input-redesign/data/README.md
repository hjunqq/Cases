# data/ — 提取物

除 `assumptions.json` 外全部由 `tools/` 生成，已 gitignore。重建：

```bash
python3 tools/extract_dispatch.py   # deck-readers / dispatcher-map / use-sites
python3 tools/deck_ast.py           # deck-ast.json / deck-ast.txt
python3 tools/dispatch_table.py     # deck-abi.json（依赖 deck-ast.json）
python3 tools/roundtrip_matrix.py   # 写到 /tmp/claude-1000/roundtrip/matrix/matrix.json，
                                    #   需要时手动拷回 data/roundtrip-matrix.json
python3 tools/verify_ast.py         # 5 项验收，必须全过
```

**`assumptions.json` 是人工写的**，不可重建：decoder 唯一被允许越过 UNKNOWN 的名字表，
每条带 `why` / `declaration` / `evidence` / `risk`。见 `18-decoder-report.md` §2。
