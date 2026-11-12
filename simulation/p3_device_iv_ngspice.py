#!/usr/bin/env python3
"""DB HiTek SVT 1.8-V MOS DC I-V device sweeps in ngspice (not HSPICE).

This tests whether both transistor types load/behave plausibly across
TT/FF/SS/FS/SF with the converted model. It does NOT establish HSPICE
numerical equivalence; that requires HSPICE or Cadence reference CSV data.
"""
from __future__ import annotations
import argparse
import csv,json,math,re,shutil
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import p3_transistor_driver as TX

CORNERS=TX.CORNER_NAMES
VDS_CASES=(0.5,1.0)
VGS_CASES=tuple(round(x*0.1,6) for x in range(19))

def netlist(corner: str, kind: str, vds: float, gate: float):
    lib=f'.include "db180_svt018_{corner}.lib"'
    if kind=="nmos":
        device="XDEV d g 0 0 nch_svt_1p8v width=1u length=0.18u multi=1"
        sources=[f"VDRAIN d 0 {vds}",f"VGATE g 0 {gate}"]
    else:
        # pchannel: D,G,S,B,SUB. Nwell/bulk to +1.8; psub to GND.
        device="XDEV d g s s 0 pch_svt_1p8v width=1u length=0.18u multi=1"
        sources=["VSUPPLY s 0 1.8",f"VDRAIN d 0 {1.8-vds}",
                 f"VGATE g 0 {1.8-gate}"]
    return "\n".join([
        f"* P3 DB HiTek {kind} DC I-V, independent ngspice-42 check",
        lib,".temp 27",*sources,device,
        ".control","set noaskquit","op","print i(vdrain)",
        "quit",".endc",".end",""])

def execute(out: Path):
    out.mkdir(parents=True,exist_ok=True)
    working=TX.ENGINE_DIR/"p3_device_iv"
    runner=TX.SpiceRunner(working)
    for corner in CORNERS:
        p=TX.model_path(corner)
        if not (working/p.name).exists() or p.stat().st_mtime>(working/p.name).stat().st_mtime:
            shutil.copy2(p,working/p.name)
    rows=[]
    for corner in CORNERS:
        for kind in ("nmos","pmos"):
            for vd in VDS_CASES:
                for gate in VGS_CASES:
                    log=runner.run(netlist(corner,kind,vd,gate),
                                   f"iv_{corner}_{kind}_{int(vd*100):03d}_{int(gate*100):03d}")
                    amp=abs(TX.spice_vector(log,"i(vdrain)"))
                    rows.append({"corner":corner,"device":kind,
                        "Vds_or_Vsd_V":vd,"Vgs_or_Vsg_V":gate,
                        "absolute_drain_current_A":amp,"W_um":1.0,"L_um":.18})
        print(f"Simulated all TT/FF/SS/FS/SF {corner} device I-V",flush=True)
    with (out/"dbhitek_ngspice_device_iv.csv").open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]))
        writer.writeheader();writer.writerows(rows)
    conditions={}
    for kind in ("nmos","pmos"):
        for corner in CORNERS:
            currents=[r for r in rows if r["device"]==kind and
                r["corner"]==corner and r["Vds_or_Vsd_V"]==.5]
            id_low=next(x["absolute_drain_current_A"] for x in currents
                if abs(x["Vgs_or_Vsg_V"]-.5)<1e-8)
            id_high=next(x["absolute_drain_current_A"] for x in currents
                if abs(x["Vgs_or_Vsg_V"]-1.5)<1e-8)
            if not(id_high>10*id_low and id_high>1e-7):
                raise AssertionError(f"{corner}/{kind}: ID at high gate voltage not plausibly higher than at low voltage")
            conditions[f"{corner}_{kind}"]={
                "Id_at_0p5V_gate_A":id_low,
                "Id_at_1p5V_gate_A":id_high,
                "on_off_ratio_at_two_biases":id_high/max(id_low,1e-20)}
    result={"status":"passed_ngspice_device_iv_sanity",
            "model":"DB HiTek 0.18um SVT MOS, zero dtemp copied wrapper",
            "simulator":"ngspice-42 ngbehavior=hs",
            "devices":["nch_svt_1p8v","pch_svt_1p8v"],
            "corners":CORNERS,"number_of_dc_runs":runner.calls,
            "calculated_sanity_checks":conditions,
            "limitations":[
               "HSPICE proprietary model-option warnings ignored by ngspice",
               "No matching HSPICE reference I-V dataset available",
               "This check does not establish current, capacitance, noise or transient accuracy against HSPICE",
               "Derived 1um/0.18um MOS test devices, not exact paper transistor dimensions",
            ]}
    (out/"dbhitek_ngspice_device_iv_summary.json").write_text(json.dumps(result,indent=2)+"\n")
    fig,axs=plt.subplots(1,2,figsize=(12,5),layout="constrained")
    for ax,kind in zip(axs,("nmos","pmos")):
        for corner in ("ff","tt","ss"):
            rr=[r for r in rows if r["device"]==kind and r["corner"]==corner
                and r["Vds_or_Vsd_V"]==.5]
            ax.semilogy([x["Vgs_or_Vsg_V"] for x in rr],
                        [max(1e-13,x["absolute_drain_current_A"]) for x in rr],
                        marker=".",label=corner.upper())
        ax.set(xlabel=("VGS" if kind=="nmos" else "VSG")+" (V)",
               ylabel="|ID| (A)",title=f"{kind.upper()} TT/FF/SS, 0.5 V D-S bias")
        ax.legend();ax.grid(alpha=.3)
    fig.savefig(out/"fig_device_dc_iv_ngspice.png",dpi=165)
    plt.close(fig)
    print(f"PASS: {runner.calls} independent MOS DC I-V ngspice runs",flush=True)
    return result

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--out",type=Path,default=Path("results/spice/p3_device_iv"))
    execute(p.parse_args().out)
