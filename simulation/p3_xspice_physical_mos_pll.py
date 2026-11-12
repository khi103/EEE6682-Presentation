#!/usr/bin/env python3
"""Independent 450-MHz PFD + physical MOS charge pump + physical 1.8-GHz VCO.

This is a TRUE in-ngspice CLOSED feedback simulation (not Python replay):
  - ngspice XSPICE digital /4 divider and 2-DFF/AND phase-frequency detector
    structurally adapted from the official ngspice XSPICE PLL example.
  - XSPICE DAC bridges convert UP-bar and DN to analog gate voltages.
  - DB HiTek 180-nm SVT MOS current source + PMOS/NMOS UP/DN switches
    and seven-bit binary-weighted NMOS pull-down elements feed real Cloop.
  - Three-stage current-starved ring CMOS MOS VCO and an input buffer
    receive the actual loop voltage. Output is divided by 4 to 450 MHz.

Reference: https://github.com/imr/ngspice/tree/master/examples/xspice/pll
Paper: Wong et al., JSSC 2004, Fig. 18-20 (NOT identical topology).
This is an independently sized physical-VCO/CP with XSPICE digital PFD,
without real data CDR, comparator or switched-capacitor ripple notch.
Numerical correlation against licensed HSPICE has not been established.
"""
from __future__ import annotations
from pathlib import Path
import argparse,csv,json,math,shutil
import p3_transistor_driver as TX
import p3_ring_vco_mos as RING

RATE_GHZ=1.8
REF_MHZ=450.0
TRIM_CODES=(0,63,127)
V_START=.96
TIME_NS=180.
VREF_BIAS=.96
LOOP_C_F=30e-12
I_SOURCE_W_UM=8.0
I_SINK_W_UM=8.0
REF_PERIOD_PS=1e12/(REF_MHZ*1e6)
CORNER="tt"

def circuit(code,corner=CORNER,initial_bias=V_START):
    lines=[
        "* INDEPENDENT PHYSICAL MOS PLL, 450MHz reference and divide-by-4",
        "* XSPICE 2-DFF PFD / digital divider; DBHiTek MOS switched pump + VCO",
        f'.include "db180_svt018_{corner}.lib"',
        ".temp 27",
        "VDD vdd 0 DC 1.8",
        f"VREFCLK refclk 0 PULSE(0 1.8 1n 5p 5p "
          f"{REF_PERIOD_PS/2-5:.10g}p {REF_PERIOD_PS:.10g}p)",
        "* XSPICE analog->digital bridges: reference and physical VCO",
        "ABRIDGE_REF [refclk] [dref] adc_ref",
        "ABRIDGE_RING [n1] [dvco] adc_ring",
        ".model adc_ref adc_bridge(in_low=.8 in_high=1.0)",
        ".model adc_ring adc_bridge(in_low=.8 in_high=1.0)",
        "* A digital four-cycle 1.8GHz to 450MHz divider",
        "ADIV4 dvco ddiv divider4",
        ".model divider4 d_fdiv(div_factor=4 high_cycles=2 i_count=0 "
           "rise_delay=1e-11 fall_delay=1e-11)",
        "* Ground and logic one (same interface as official ngspice example)",
        "VZERO z 0 DC 0",
        "ABRIDGE_ZERO [z] [dzero] adc_ref",
        "AINVONE dzero done inv_one",
        ".model inv_one d_inverter(rise_delay=1e-11 fall_delay=1e-11)",
        "* PFD: reference leads => up; divider leads => down.",
        "XPF dref ddiv dUP dUPbar dDN dDNbar pfd",
        "ABRIDGE_DAC [dUPbar dDN] [upbar dngate] dac_out",
        ".model dac_out dac_bridge(out_low=0 out_high=1.8 "
            "out_undef=.9 input_load=5e-15 t_rise=8e-12 t_fall=8e-12)",
        ".subckt pfd d_R d_V d_U d_Ubar d_D d_Dbar",
        "ANDRESET [d_U d_D] dreset and2",
        ".model and2 d_and(rise_delay=1e-11 fall_delay=1e-11 input_load=5e-15)",
        "ADFFREF done d_R dzero dreset d_U d_Ubar flop",
        "ADFFFB done d_V dzero dreset d_D d_Dbar flop",
        ".model flop d_dff(clk_delay=1e-11 set_delay=1e-11 "
          "reset_delay=1e-11 ic=2 rise_delay=1e-11 fall_delay=1e-11)",
        ".ends pfd",
        "* Physical 7-bit charge pump with transistor switches.",
        "VBPMOS pbias 0 .95",
        "VBNMOS nbias 0 .68",
        "XPSOURCE psrc pbias vdd vdd 0 pch_svt_1p8v "
          f"width={I_SOURCE_W_UM}u length=.36u multi=1",
        "XPSW loopctrl upbar psrc vdd 0 pch_svt_1p8v "
          "width=12u length=.18u multi=1",
        "XNSW loopctrl dngate nsink 0 nch_svt_1p8v "
          "width=12u length=.18u multi=1",
        "XNSINKBASE nsink nbias 0 0 nch_svt_1p8v "
          f"width={I_SINK_W_UM}u length=.36u multi=1",
    ]
    for w in (1,2,4,8,16,32,64):
        lines += [
           f"VCBIT{w} trim{w} 0 {0.55 if code&w else 0.}",
           f"XNSINK{w} nsink trim{w} 0 0 nch_svt_1p8v "
               f"width=.48u length=.36u multi={w}",
        ]
    lines += [
        "* Physical loop capacitor and bias-stabilizing resistive path.",
        f"VSTART vstart 0 {initial_bias:.7g}",
        f"CLOOP loopctrl 0 {LOOP_C_F:.10g} ic={initial_bias:.7g}",
        "RLEAK loopctrl vstart 5e8",
        "BNB nb 0 V={min(max(v(loopctrl),.65),1.65)}",
        "BPB pb 0 V={1.8-v(nb)}",
    ]
    for i in range(1,RING.STAGES+1):
        node=f"n{i}"
        prev=f"n{i-1}" if i>1 else f"n{RING.STAGES}"
        lines += [
           f"XPVCO_MAIN{i} {node} {prev} pv{i} vdd 0 pch_svt_1p8v width=4u length=.18u multi=1",
           f"XPVCO_STARVE{i} pv{i} pb vdd vdd 0 pch_svt_1p8v width=4u length=.18u multi=1",
           f"XNVCO_MAIN{i} {node} {prev} nv{i} 0 nch_svt_1p8v width=2u length=.18u multi=1",
           f"XNVCO_STARVE{i} nv{i} nb 0 0 nch_svt_1p8v width=2u length=.18u multi=1",
           f"CVCO_LOAD{i} {node} 0 {RING.CL_F:.9g}",
        ]
    lines += [
        ".ic "+" ".join(f"v(n{i})={'1.8' if i%2 else '0'}" for i in range(1,RING.STAGES+1)),
        ".control","set noaskquit",
        f"tran 3p {TIME_NS}n uic",
        "wrdata physical_pll.csv time v(n1) v(refclk) v(loopctrl) "
           "v(upbar) v(dngate) i(vdd)",
        "quit",".endc",".end",
    ]
    return "\n".join(lines)+"\n"

def read(path):
    rows=[]
    for line in path.read_text().splitlines():
        try: a=[float(x) for x in line.split()]
        except ValueError: continue
        if len(a)>=14 and all(math.isfinite(x) for x in a):
            rows.append({
               "time_s":a[0],"vco_V":a[3],"ref_V":a[5],"control_V":a[7],
               "UPbar_V":a[9],"DN_V":a[11],"vdd_A":a[13]})
    if len(rows)<400:
        raise RuntimeError(f"XSPICE PLL waveform missing rows {len(rows)}")
    return rows

def rising(rows,key,threshold=.9,start_ns=0):
    t=[]
    for a,b in zip(rows,rows[1:]):
        if a["time_s"]<start_ns*1e-9:continue
        x,y=a[key],b[key]
        if x<threshold<=y:
            t.append(a["time_s"]+(threshold-x)*(b["time_s"]-a["time_s"])/(y-x))
    return t

def metrics(rows):
    vco=rising(rows,"vco_V",start_ns=TIME_NS-40.)
    ref=rising(rows,"ref_V",start_ns=TIME_NS-40.)
    d=[b-a for a,b in zip(vco,vco[1:])]
    r=[b-a for a,b in zip(ref,ref[1:])]
    if len(d)<15:return {"periods":len(d),"vco_GHz":None,
                             "control_last_V":rows[-1]["control_V"]}
    mean=sum(d)/len(d)
    vco_f=1/mean/1e9
    ref_f=1/(sum(r)/len(r))/1e6 if r else None
    ctl=[x["control_V"] for x in rows if x["time_s"]>=(TIME_NS-30)*1e-9]
    return {
        "vco_GHz":vco_f,
        "reference_MHz":ref_f,
        "vco_period_rms_ps":math.sqrt(sum((p-mean)**2 for p in d)/len(d))*1e12,
        "control_mean_V":sum(ctl)/len(ctl),
        "control_delta_last_30ns_mV":(max(ctl)-min(ctl))*1e3,
        "control_last_V":rows[-1]["control_V"],
        "pump_UPbar_mean_V":sum(r["UPbar_V"] for r in rows[-1000:])/1000.,
        "pump_DN_mean_V":sum(r["DN_V"] for r in rows[-1000:])/1000.,
        "periods":len(d)
    }

def main(out):
    out.mkdir(parents=True,exist_ok=True)
    work=TX.ENGINE_DIR/"p3_physical_xspice_pll"
    runner=TX.SpiceRunner(work)
    model=TX.model_path(CORNER)
    target=work/model.name
    if not target.exists() or model.stat().st_mtime>target.stat().st_mtime:
        shutil.copy2(model,target)
    cases={}
    for code in TRIM_CODES:
        txt=runner.run(circuit(code),f"pfd_vco_cp_code_{code}")
        wave=read(work/"physical_pll.csv")
        m=metrics(wave)
        cases[str(code)]=m
        print(f"XSPICE PFD -> switched MOS CP -> physical MOS VCO "
              f"code={code} fVCO={m.get('vco_GHz')}GHz "
              f"VCTRL={m['control_last_V']:.4f}V "
              f"VCTRLpp={m.get('control_delta_last_30ns_mV')}mV",flush=True)
        if code==63:
            with (out/"xspice_pfd_mos_cp_vco_code63_waveform.csv").open("w",newline="") as f:
                step=max(1,len(wave)//25000)
                wr=csv.DictWriter(f,fieldnames=list(wave[0]))
                wr.writeheader();wr.writerows(wave[::step])
    result={
      "status":"executed_xspice_digital_PFD_transistor_MOS_CP_VCO_closed_loop",
      "basis":"ngspice official examples/xspice/pll/f-p-det-d-sub.cir structurally adapted",
      "physical_components":"DB HiTek 180nm MOS seven-bit switched charge pump, tunable VCO, C-loop",
      "behavioral_components":"XSPICE 2-DFF and reset AND PFD, digital 1:4 divider, DAC/ADC bridges",
      "reference_MHz":REF_MHZ,"divider":4,"target_output_GHz":RATE_GHZ,
      "simulation_duration_ns":TIME_NS,
      "per_code":cases,"ngspice_runs":runner.calls,
      "full_original_paper_PLL":False,
      "limitations":[
        "No exact paper device sizes/physical PFD or switched-capacitor ripple filter",
        "PLL frequency lock requires stability/phase-jitter verification in addition to this sweep",
        "No data-driven bang-bang CDR; only 450-MHz reference PLL",
        "No simultaneous MOS TX/channel/RX connections in this PLL-only simulation",
        "HSPICE/ngspice PDK numeric correlation still missing",
      ]
    }
    (out/"xspice_mos_pfd_cp_pll_results.json").write_text(json.dumps(result,indent=2)+"\n")
    if not any(v.get("vco_GHz") and abs(v["vco_GHz"]-RATE_GHZ)<.06 for v in cases.values()):
        raise AssertionError("Official XSPICE PFD + physical MOS pump/VCO did not capture 1.8 GHz")
    print("PASS: XSPICE PFD/4 and physical MOS charge pump/VCO demonstrated near-target frequency in at least one code",flush=True)
    return result

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--out",type=Path,
                   default=Path("results/spice/p3_xspice_real_mos_pll"))
    main(p.parse_args().out)
