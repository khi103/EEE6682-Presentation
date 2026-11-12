#!/usr/bin/env python3
"""Independently audit 45 Gear/MOS PLL PVT cases versus earlier 45/45 default.

Do not trust GitHub Actions job success as electrical pass. Each
available completed physical ngspice transient must cover 1200ns,
have an explicit JSON Boolean electrical screen, finite metrics and
all 5 process x 3 temperature x 3 voltage tuples represented once.

Produce machine-readable PASS/FAIL CSV, JSON and human-readable
engineering Markdown. One failure refutes all-PVT numerical robustness
for the chosen fixed reconstructed MOS PLL design.
"""
from __future__ import annotations
import argparse,csv,json,math
from pathlib import Path

CORNERS=("tt","ff","ss","fs","sf")
TEMPS=(-20.,27.,85.)
VDDS=(1.71,1.80,1.89)
DESIGN="diode_w8_r8k"

def run(inp,out):
    out.mkdir(parents=True,exist_ok=True)
    found={}
    for p in inp.rglob("gear_PVT_*.json"):
        item=json.loads(p.read_text())
        k=(item["corner"],float(item["temperature_C"]),float(item["supply_V"]))
        if k in found:raise RuntimeError(f"Duplicate simulated PVT {k}: {p}")
        if item.get("design")!=DESIGN:raise RuntimeError(f"Unexpected device design {p}")
        last=item.get("waveform_last_ns")
        if last is not None and not math.isfinite(float(last)):
            raise ValueError(f"Nonfinite time {p}")
        found[k]=item
    expected={(c,t,v) for c in CORNERS for t in TEMPS for v in VDDS}
    if found.keys()!=expected:
        raise RuntimeError(f"Missing PVT {sorted(expected-set(found))}, extra {sorted(set(found)-expected)}")
    rows=[]
    for k in sorted(expected):
        r=found[k]
        metrics=["VCO_frequency_GHz","phase_std_ps",
                 "physical_VCO_gate_ripple_mVpp",
                 "last_three_disjoint_80ns_frequency_drift_MHz"]
        for f in metrics:
            x=r.get(f)
            if x is not None and not math.isfinite(float(x)):
                raise RuntimeError(f"Nonfinite electrical measurement in {k}, {f}")
        pass_e=bool(r["qualified_after_completeness"])
        if pass_e and not r.get("complete_1p2us_transient",False):
            raise AssertionError(f"False positive, truncated physical MOS run: {k}")
        rows.append({
            "corner":k[0],"temp_C":k[1],"VDD_V":k[2],
            "simulator":"ngspice42 Gear 3ps",
            "VCO_GHz":r["VCO_frequency_GHz"],
            "phaseSTD_ps":r["phase_std_ps"],
            "VCOgate_ripple_mVpp":r["physical_VCO_gate_ripple_mVpp"],
            "3_disjoint_windows_drift_MHz":r["last_three_disjoint_80ns_frequency_drift_MHz"],
            "last_cycle_slips":r["last_reference_cycle_slips"],
            "waveform_last_ns":r["waveform_last_ns"],
            "physically_simulated_full_duration":r["complete_1p2us_transient"],
            "electrical_pass":pass_e,
        })
    with (out/"gear45_detailed_PVT.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    fails=[r for r in rows if not r["electrical_pass"]]
    summary={
        "scope":"DB HiTek 180nm independently reconstructed MOS ring+CP reference PLL",
        "design":DESIGN,"method":"Gear 3ps independent solver of default/trap 3ps",
        "total_expected":45,"physically_simulated_complete":
           sum(r["physically_simulated_full_duration"] for r in rows),
        "electrical_passes":len(rows)-len(fails),
        "electrical_failures":len(fails),
        "failed_cases":fails,
        "default_3ps_original_PVT_screen":"45/45, run 43253822240",
        "all_PVT_numerical_robustness_proven":len(fails)==0,
        "original_2004_foundry_model_reproduced":False,
        "data_CDR_silicon_lock_proven":False}
    (out/"gear45_summary.json").write_text(json.dumps(summary,indent=2)+"\n")
    lines=[
       "# Independent Gear MOS PLL PVT audit",
       "",
       "Original reference: fixed physical 180nm MOS PMOS diode-bias PLL, XSPICE 450MHz external reference.",
       "",
       f"**Gear 3ps: {summary['electrical_passes']}/45 pass, {summary['physically_simulated_complete']}/45 full transients.**",
       "",
       "The original default-trap 3ps 45/45 count is not a solver-independent proof.",
       "",
       "| Process | Temperature (°C) | VDD (V) | VCO (GHz) | Phase STD (ps) | Drift (MHz) | Cycle slips | Status |",
       "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for r in rows:
        num=lambda k: ("n/a" if r[k] is None else f"{float(r[k]):.5f}")
        lines.append(
          f"| {r['corner'].upper()} | {r['temp_C']:.0f} | {r['VDD_V']:.2f} "
          f"| {num('VCO_GHz')} | {num('phaseSTD_ps')} "
          f"| {num('3_disjoint_windows_drift_MHz')} | {r['last_cycle_slips']} "
          f"| {'PASS' if r['electrical_pass'] else 'FAIL'} |")
    lines+=["","This does not prove original ASIC, random jitter, BER or PDK model correlation."]
    (out/"gear45_audit.md").write_text("\n".join(lines)+"\n")
    print(f"GEAR45_AUDIT completed={summary['physically_simulated_complete']}/45 "
          f"electrical_pass={summary['electrical_passes']}/45",flush=True)
    for r in fails:
        print(f"GEAR45_FAIL corner={r['corner']} T={r['temp_C']} VDD={r['VDD_V']} "
              f"phase_std={r['phaseSTD_ps']} drift={r['3_disjoint_windows_drift_MHz']} "
              f"slips={r['last_cycle_slips']} last_ns={r['waveform_last_ns']}",flush=True)
    return summary

if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("--in-dir",type=Path,required=True)
    a.add_argument("--out",type=Path,default=Path("results/audit/p3_Gear45_PVT"))
    v=a.parse_args();run(v.in_dir,v.out)
