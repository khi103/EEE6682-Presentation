#!/usr/bin/env python3
"""P3 Fig.18/20-inspired 450MHz MOS switched-capacitor HOLD filter experiment.

Compares TWO independent ngspice 450MHz digital-PFD / physical MOS-CP /
MOS-ring-VCO closed-loop circuits:
  A: verified passive 700ohm + 8pF VCO bias postfilter.
  B: sample-and-hold VCO bias with ACTUAL complementary NMOS/PMOS
     transmission gate clocked by 450MHz reference, and 8pF HOLD cap.

This is NOT the author's exact switched-capacitor notch filter.
We measure spectral projection of the 450MHz VCO-control ripple,
phase-error std, frequency, control ripple and worst-case. The
source circuits and PDK models are fixed except postfilter topology.
"""
from __future__ import annotations
import argparse,csv,json,math,shutil
from pathlib import Path
import p3_transistor_driver as TX
import p3_xspice_physical_mos_pll as PLL

REF_HZ=450e6
CODE=63

def deck(is_switched:bool):
    source=PLL.circuit(CODE,corner="tt",initial_bias=PLL.V_START)
    if not is_switched:return source
    assert "RPOST loopctrl vcobias 700" in source
    source=source.replace("RPOST loopctrl vcobias 700",
      "* RPOST removed: actual complementary CMOS sample/hold MOS switches")
    extras=[
      "* Physically switched 450MHz VCO-control sampling gate",
      "XPCLKINV sampleclkb refclk vdd vdd 0 pch_svt_1p8v "
         "width=4u length=.18u multi=1",
      "XNCLKINV sampleclkb refclk 0 0 nch_svt_1p8v "
         "width=2u length=.18u multi=1",
      "XNTG vcobias refclk loopctrl 0 nch_svt_1p8v "
         "width=14u length=.18u multi=1",
      "XPTG vcobias sampleclkb loopctrl vdd 0 pch_svt_1p8v "
         "width=28u length=.18u multi=1",
    ]
    return source.replace(".control","\n".join(extras)+"\n.control",1)

def fourier_amplitude(rows,field,frequency_Hz=REF_HZ):
    samples=[x for x in rows if x["time_s"]>=(PLL.TIME_NS-45.)*1e-9]
    if len(samples)<1000:raise RuntimeError("Insufficient steady-state samples")
    total_time=samples[-1]["time_s"]-samples[0]["time_s"]
    average=sum(.5*(a[field]+b[field])*(b["time_s"]-a["time_s"])
                for a,b in zip(samples,samples[1:]))/total_time
    sum_re=sum_im=0.
    for a,b in zip(samples,samples[1:]):
        dt=b["time_s"]-a["time_s"]
        ta,tb=a["time_s"],b["time_s"]
        ia=(a[field]-average)
        ib=(b[field]-average)
        sum_re+=.5*dt*(ia*math.cos(2*math.pi*frequency_Hz*ta)+
                         ib*math.cos(2*math.pi*frequency_Hz*tb))
        sum_im+=.5*dt*(ia*math.sin(2*math.pi*frequency_Hz*ta)+
                         ib*math.sin(2*math.pi*frequency_Hz*tb))
    return 2*math.hypot(sum_re,sum_im)/total_time

def save(path,rows):
    with path.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]))
        w.writeheader();w.writerows(rows)

def main(out):
    out.mkdir(parents=True,exist_ok=True)
    work=TX.ENGINE_DIR/"p3_mos_switched_cap_filter"
    runner=TX.SpiceRunner(work)
    model=TX.model_path("tt")
    copy=work/model.name
    if not copy.exists() or model.stat().st_mtime>copy.stat().st_mtime:
        shutil.copy2(model,copy)
    cases={}
    for switched in (False,True):
        label="MOS_switch_hold_450MHz" if switched else "passive_R700_C8p"
        runner.run(deck(switched),label)
        rows=PLL.read(work/"physical_pll.csv")
        m=PLL.metrics(rows)
        m.update(PLL.aligned_phase_errors_ps(rows))
        m["450MHz_VCO_bias_spur_amplitude_mV"]=(
            fourier_amplitude(rows,"physical_vco_gate_bias_V")*1e3)
        m["450MHz_CP_loop_node_spur_amplitude_mV"]=(
            fourier_amplitude(rows,"control_V")*1e3)
        m["frequency_near_1p8GHz"]=bool(m.get("vco_GHz") and
                                     abs(m["vco_GHz"]-1.8)<.012)
        m["phase_stable"]=bool(m.get("std_phase_ps") is not None
                               and m["std_phase_ps"]<8)
        cases[label]=m
        # Preserve 5k points from last 60ns for independent plotting.
        final=[r for r in rows if r["time_s"]>=(PLL.TIME_NS-60)*1e-9]
        save(out/f"{label}_mos_vco_bias_waveform.csv",
             final[::max(1,len(final)//5000)])
        print(f"450MHz filter {label}: freq={m.get('vco_GHz')}GHz "
              f"phaseSTD={m.get('std_phase_ps')}ps "
              f"bias_450MHz={m['450MHz_VCO_bias_spur_amplitude_mV']:.4f}mVamp "
              f"gate_ripple_pp={m.get('physical_vco_gate_ripple_mV')}mVpp",
              flush=True)
    a=cases["passive_R700_C8p"]["450MHz_VCO_bias_spur_amplitude_mV"]
    b=cases["MOS_switch_hold_450MHz"]["450MHz_VCO_bias_spur_amplitude_mV"]
    report={
       "status":"measured_P3_inspired_MOS_switched_cap_hold_450MHz_vs_passive_filter",
       "source":"DB HiTek 180nm MOS 7-bit CP/VCO, ngspice XSPICE PFD/4",
       "sampling_frequency_MHz":450,
       "filters":{
         "passive":"700ohm + 8pF continuously coupled VCO gate",
         "switched":"actual MOS complementary transmission gate driven at 450MHz + 8pF hold capacitor",
       },
       "conditions":cases,
       "450MHz_bias_spur_ratio_switched_over_passive":b/a if a>0 else None,
       "physical_P3_SC_filter_exact":False,
       "limitations":[
         "A conventional transmission-gate sample/hold is NOT the published exact switched-capacitor ripple-notch topology",
         "Ripple from deterministic MOS/PFD transitions does not capture phase noise or random jitter",
         "No original 2004 chip filter capacitor sizes, layout, physical PFD transistor or HSPICE matching",
       ]
    }
    (out/"MOS_450MHz_switched_cap_filter_summary.json").write_text(json.dumps(report,indent=2)+"\n")
    if not cases["passive_R700_C8p"]["phase_stable"]:
        raise AssertionError("Previously verified passive-filter PLL lost phase stability")
    print("PASS: physically sampled MOS VCO control and passive reference measured and compared",flush=True)
    return report

if __name__=="__main__":
    arg=argparse.ArgumentParser()
    arg.add_argument("--out",type=Path,
           default=Path("results/spice/p3_mos_switched_cap_filter"))
    main(arg.parse_args().out)
