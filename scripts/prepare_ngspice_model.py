#!/usr/bin/env python3
"""Create a local ngspice-compatible copy of a DB HiTek SVT subset.

The HSPICE SVT wrapper forwards dtemp=dtemp to two BSIM3 MOS devices
and one body diode. ngspice-42 rejects per-instance dtemp for BSIM3.
For the *default dtemp=0* smoke test, remove that forwarding on copies.

NO foundry model parameters are stored in this script or committed.
This does not establish compatibility or accuracy relative to HSPICE.
Use circuit-wide .temp for later temperature sweeps, and do not claim
equivalence for nonzero per-device dtemp.
"""
from pathlib import Path
import argparse
import re

INSTANCE = re.compile(r"^\s*(?:m\w+|d\w+)\s", re.IGNORECASE)
DTEMP_FORWARD = re.compile(r"(?i)(?<=\s)dtemp\s*=\s*dtemp(?=\s|$)")

def convert(source: Path, destination: Path) -> int:
    if source.resolve() == destination.resolve():
        raise ValueError("Refusing to overwrite the original foundry model")
    lines = source.read_text(encoding="latin-1").splitlines(keepends=True)
    changed = []
    replaced = 0
    for line in lines:
        if INSTANCE.match(line) and DTEMP_FORWARD.search(line):
            line, count = DTEMP_FORWARD.subn("", line)
            replaced += count
        changed.append(line)
    if replaced != 3:
        raise ValueError(
            f"Expected exactly 3 forwarded dtemp tokens in two MOS and one "
            f"diode instance, found {replaced}. Do not auto-modify unknown PDK."
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("".join(changed), encoding="latin-1")
    print(f"Created ngspice-only copy: {destination}")
    print("Removed 3 HSPICE dtemp forwarding tokens from MOS/diode instances.")
    print("Original file unchanged; HSPICE-only model warnings may remain.")
    return replaced

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("source", type=Path)
    p.add_argument("destination", type=Path)
    args = p.parse_args()
    convert(args.source, args.destination)
