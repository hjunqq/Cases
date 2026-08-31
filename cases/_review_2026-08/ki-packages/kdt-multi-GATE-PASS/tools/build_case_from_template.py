#!/usr/bin/env python3
"""build_case_from_template — COPY-FIRST entry point for every HSTAR case.

Capability 1/30 of docs/capabilities.md. This is the FIRST tool to run for any new case.

HSTAR has no CLI arguments and no self-describing input format: it reads a file literally named
`inp` from the current directory, takes the case base name `probn` from line 4, and then opens
~35 files called `<probn>.<ext>`. Several of those are only read when a counter elsewhere is
non-zero, and every header/echo line is a positional placeholder. A case written from scratch
gets the RECORD SEQUENCE wrong and fails with `forrtl: severe (24): end-of-file during read`
-- or worse, reads on past a short line and silently produces a different model.

So: never generate a case. Copy a case that runs, then edit values in place.

    python3 build_case_from_template.py --template static --dest /tmp/mycase --runblks 2
    python3 build_case_from_template.py --list

validate -> process -> validate:
  * validates the template exists and is a real HSTAR case (has `inp`),
  * copies the whole directory and makes it writable,
  * validates the copy: .glb parses, .cor/.ele record counts match npoin/nelem.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hstar_io import (TEMPLATES, GlbDoc, HstarInputError, check_consistent,  # noqa: E402
                       copy_template, probn_of, set_inp)


def build(template="static", dest=None, probn=None, runblks=None, restart=None,
          overwrite=False):
    """Copy a template case and wire up `inp`. Returns a summary dict."""
    if dest is None:
        raise HstarInputError("dest is required")
    case = copy_template(template, dest, overwrite=overwrite)

    # -- process: rename the probn-prefixed files if a new base name was asked for
    old = probn_of(case)
    if probn and probn != old:
        for p in sorted(case.glob(f"{old}.*")) + sorted(case.glob(f"{old}[a-z]*.*")):
            p.rename(p.with_name(p.name.replace(old, str(probn), 1)))
    set_inp(case, probn=probn or old, runblks=runblks, restart=restart)

    # -- validate the copy
    info = check_consistent(case)
    if not info["ok"]:
        raise HstarInputError(
            f"template copy is inconsistent: {info['problems']} -- the template itself is "
            f"broken, do not proceed")
    info["template"] = str(TEMPLATES.get(template, template))
    info["case_dir"] = str(case)
    return info


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--list", action="store_true", help="list known templates and exit")
    ap.add_argument("--template", default="static")
    ap.add_argument("--dest")
    ap.add_argument("--probn", help="new case base name (default: keep the template's)")
    ap.add_argument("--runblks", type=int, help="how many load blocks to execute")
    ap.add_argument("--restart", type=int, choices=[0, 1, 2],
                    help="0 fresh, 1 resume from .rtt, 2 post-process only")
    ap.add_argument("--overwrite", action="store_true")
    a = ap.parse_args(argv)
    if a.list:
        for k, v in sorted(TEMPLATES.items()):
            print(f"{k:28} {'OK ' if Path(v).is_dir() else 'MISSING'} {v}")
        return 0
    if not a.dest:
        ap.error("--dest is required (or use --list)")
    info = build(a.template, a.dest, a.probn, a.runblks, a.restart, a.overwrite)
    print(json.dumps(info, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
