#!/usr/bin/env python3
"""Independent 90-case MOS PLL PVT aggregation from immutable Action artifacts.

Two *fixed* reconstructed real-diode-PMOS bias circuits each run the
same 5 process corners x 3 temperatures x 3 supply voltages = 45
distinct combinations. Read the original 42 successful electrically
tested designs' report JSONs from Actions run 43244846868 and the
missing 48 from Actions run 43252309753. Reject duplicates, missing
cases, aborted simulations, and failures even when GitHub Actions
calls a job success. Retain every individual numeric measurement.

No regression or PHY claims are made for original 2004 ASIC, foundry
mismatch statistics, random jitter, power or full serial-data CDR.
"""
from __future__ import annotations
import argparse,csv,json,math
from pathlib import Path

DESIGNS=("diode_w16_r4k","diode_w8_r8k")
CORNERS=("tt","ff","ss","fs","sf")
TEMPS=(-20.,27.,85.)
VDDS=(1.71,1.8,1.89)

def parse(input_dir):
    rows={}
    missing=[]
    files=list(input_dir.rglob("*_physical_bias_PVT.json"))+list(input_dir.rglob("grid_*.json"))
    if not files:raise RuntimeError("Missing original saved electrical artifacts")
    for p in files:
        obj=json.loads(p.read_text())
        if p.name.startswith("grid_"):
            v=obj["measured"]
        else:
            v=obj
        d=v["design"]
        c=v["PVT_process_corner"]
        t=float(v["temperature_C"])
        s=float(v["supply_V"])
        if d not in DESIGNS or c not in CORNERS or t not in TEMPS or s not in VDDS:
            raise ValueError(f"Unexpected PVT tuple in {p}: {(d,c,t,s)}")
        k=(d,c,t,s)
        if k in rows:
            raise RuntimeError(f"DUPLICATE foundry MOS PVT point: {k}, files {rows[k]['source']} {p}")
        passflag=v["electrical_screen_passed"]
        if not isinstance(passflag,bool):
            raise AssertionError(f"Unqualified electrical screen type {p}: {passflag}")
        record={
          "design":d,"corner":c,"temperature_C":t,"VDD_V":s,
          "fVCO_GHz":v["VCO_frequency_GHz"],
          "reference_phase_std_ps":v["reference_phase_std_ps"],
          "MOS_gate_ripple_mVpp":v["physical_VCO_gate_ripple_mVpp"],
          "last_3_window_drift_MHz":v["last_disjoint_window_freq_drift_MHz"],
          "last_reference_cycle_slips":v["last_reference_cycle_slips"],
          "electrical_pass":passflag,
          "simulator_status":v["status"],
          "source":str(p.relative_to(input_dir)),
        }
        if record["simulator_status"]!="ran" and record["simulator_status"]!="simulated":
            raise AssertionError(f"Electrical job not simulated: {p}")
        rows[k]=record
    expected={(d,c,t,v) for d in DESIGNS for c in CORNERS for t in TEMPS for v in VDDS}
    extra=set(rows)-expected
    missing=expected-set(rows)
    if missing or extra:
        raise AssertionError(f"Missing {len(missing)}, extra {len(extra)}; missing={sorted(missing)[:12]}")
    return [rows[k] for k in sorted(rows)]

def run(input_dir,out):
    out.mkdir(parents=True,exist_ok=True)
    cases=parse(input_dir)
    summary={}
    for d in DESIGNS:
        selected=[x for x in cases if x["design"]==d]
        passed=sum(x["electrical_pass"] for x in selected)
        failures=[x for x in selected if not x["electrical_pass"]]
        summary[d]={
          "attempted":len(selected),"electrical_passed":passed,
          "electrical_failed":len(failures),
          "failed_PVT_cases":failures,
          "max_phase_error_std_ps":max(float(x["reference_phase_std_ps"]) for x in selected),
          "max_vco_gate_ripple_mVpp":max(float(x["MOS_gate_ripple_mVpp"]) for x in selected),
          "max_three_window_frequency_span_MHz":max(float(x["last_3_window_drift_MHz"]) for x in selected),
          "max_reference_cycle_slip_count":max(int(x["last_reference_cycle_slips"]) for x in selected),
          "min_vco_GHz":min(float(x["fVCO_GHz"]) for x in selected),
          "max_vco_GHz":max(float(x["fVCO_GHz"]) for x in selected),
        }
        print(f"COMPLETE_PHYSICAL_MOS_PVT design={d} "
              f"electrical_pass={passed}/{len(selected)} "
              f"max_phase_std_ps={summary[d]['max_phase_error_std_ps']:.5f} "
              f"max_gate_ripple_mV={summary[d]['max_vco_gate_ripple_mVpp']:.5f} "
              f"max_window_span_MHz={summary[d]['max_three_window_frequency_span_MHz']:.5f} "
              f"max_cycle_slips={summary[d]['max_reference_cycle_slip_count']}",flush=True)
    report={
       "source_original_21_each":"https://github.com/khi103/EEE6682-Presentation/actions/runs/43244846868",
       "source_extra_24_each":"https://github.com/khi103/EEE6682-Presentation/actions/runs/43252309753",
       "test_type":"physical diode-biased MOS PLL with 450MHz ideal XSPICE PFD/4",
       "frequency_target_GHz":1.8,
       "processes":CORNERS,"temperatures_C":TEMPS,"core_supplies_V":VDDS,
       "one_fixed_circuit_per_design":True,
       "total_distinct_electrical_points":len(cases),
       "two_model_designs":summary,
       "all_cases":cases,
       "does_not_prove_random_jitter_or_original_2004_silicon":True,
    }
    (out/"complete_90_point_mos_pll_pvt.json").write_text(json.dumps(report,indent=2)+"\n")
    with (out/"complete_90_point_mos_pll_pvt.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(cases[0]))
        w.writeheader();w.writerows(cases)
    if any(v["electrical_failed"] for v in summary.values()):
        print("WARNING: At least one MOS PVT electrical qualification failed, see artifact",flush=True)
    return report

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--input",type=Path,required=True)
    p.add_argument("--out",type=Path,default=Path("results/audit/p3_90PVT"))
    a=p.parse_args()
    run(a.input,a.out)
