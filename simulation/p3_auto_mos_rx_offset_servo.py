#!/usr/bin/env python3
"""In-SPICE automatic MOS receiver threshold-reference compensation.

A real 180nm MOS current-sink device (effective 9x 0.48um width),
a resistor-sourced 280-mV *deliberately offset* RX reference node,
a physical capacitor, and an idealized continuous-time error integrator
are connected in the SAME ngspice TX/PLL/RX simulation.

The controller senses ONLY actual v(vref_rx) minus a fixed 250-mV
reference; it NEVER reads transmitted PRBS, BER or RX latch decisions.
It adjusts a physical MOSFET's gate voltage through a behavioral
B-source. This is an independent closed-loop *analog* reference
calibration study, NOT the original Wong 2004 Fig.14 digitally
calibrated 4-bit/current-steering offset cancellation and NOT PDK
mismatch Monte Carlo.

Physical TX 8:4:2:1 MOS, RC2 channel, MOS RX latches, MOS switched
charge pump, MOS VCO and XSPICE 450MHz PFD share the deck. 512-bit PRBS31
holdout scoring [144,502) uses only post-run training-derived lag.
"""
from __future__ import annotations
import argparse,csv,json,math,shutil
from pathlib import Path
import p3_transistor_driver as TX
import p3_mos_rx_offset_stress as OFFSET
import p3_reference_pll_integrated_mos_link as LINK

BITS=512
GMS=(0.,.00010,.00050)
ALPHAS=(0.,.30)
REFERENCE_SOURCE=.280
TARGET=.250
INITIAL_GATE=.35
C_INTEGRATOR=5e-12

def deck(bits,alpha,gm):
    d=OFFSET.netlist(bits,alpha,30.)
    anchor="VREF_RX vref_rx 0 DC 0.280000000"
    if d.count(anchor)!=1:raise RuntimeError("Unexpected RX offset reference")
    lines=[
      "* Independent physical-MOS analog reference servo and RC filter",
      f"VREFBASE vrefbase 0 DC {REFERENCE_SOURCE:.6f}",
      "RREFAUTO vrefbase vref_rx 3000",
      f"CREFDECAP vref_rx 0 100f ic={REFERENCE_SOURCE:.6f}",
      "XNRXAUTO vref_rx gatecal 0 0 nch_svt_1p8v width=.48u length=.36u multi=9",
      f"VREF_TARGET calref 0 DC {TARGET:.6f}",
      f"VSTARTCAL calstart 0 DC {INITIAL_GATE:.6f}",
      f"CCAL_V trimstate 0 {C_INTEGRATOR:.10g} ic={INITIAL_GATE:.6f}",
      "RLEAK_CAL trimstate calstart 300meg",
      "BVG_CAL gatecal 0 V={min(max(v(trimstate),0.0),1.2)}",
      f"BCAL_I trimstate 0 I={{ -{gm:.8g}*(v(vref_rx)-v(calref)) }}",
    ]
    d=d.replace(anchor,"\n".join(lines),1)
    d=d.replace(".control",
       f".ic v(vref_rx)={REFERENCE_SOURCE:.6f} v(trimstate)={INITIAL_GATE:.6f}\n.control",1)
    a="quit\n.endc"
    if d.count(a)!=1:raise RuntimeError("ngspice control not unique")
    d=d.replace(a,
        "wrdata rx_auto_ref_wave.csv time v(vref_rx) v(gatecal) v(trimstate)\nquit\n.endc",1)
    return d

def statistics(path,start_ns,stop_ns):
    arr=[]
    for s in path.read_text().splitlines():
        try:a=[float(x) for x in s.split()]
        except ValueError:continue
        if len(a)>=8 and all(math.isfinite(x) for x in a):
            arr.append({"time_s":a[0],"vref":a[3],"gate":a[5],"state":a[7]})
    if len(arr)<100:raise RuntimeError("No calibration waveform")
    before=[r for r in arr if start_ns-10<=r["time_s"]*1e9<start_ns]
    after=[r for r in arr if start_ns<=r["time_s"]*1e9<=stop_ns]
    last=after[-min(1000,len(after)):]
    return {
      "pre_data_reference_mV":sum(r["vref"] for r in before)/len(before)*1000 if before else None,
      "during_last_data_reference_mV":sum(r["vref"] for r in last)/len(last)*1000,
      "during_last_data_gate_V":sum(r["gate"] for r in last)/len(last),
      "post_data_reference_min_mV":min(r["vref"] for r in after)*1000,
      "post_data_reference_max_mV":max(r["vref"] for r in after)*1000,
    }

def main(out,alpha,gm):
    if alpha not in ALPHAS or gm not in GMS:raise ValueError
    out.mkdir(parents=True,exist_ok=True)
    label=f"alpha_{alpha:.2f}_gm_{gm*1e6:.0f}uAperV".replace(".","p")
    work=TX.ENGINE_DIR/("p3_auto_RX_offset_"+label)
    runner=TX.SpiceRunner(work)
    model=TX.model_path("tt");dst=work/model.name
    if not dst.exists() or model.stat().st_mtime>dst.stat().st_mtime:
        shutil.copy2(model,dst)
    old=LINK.BITS
    result={"mode":"automatically controlled MOS current-sink RX offset reference",
      "alpha":alpha,"charge_integrator_gm_A_per_V":gm,
      "external_TX_ground_truth_drives_calibration":False,
      "physical":"MOS TX, MOS receiver latch, MOS VCO and charge pump, single circuit",
      "behavioral":"continuous-time reference voltage error controller, XSPICE reference PFD",
      "not_actual_2004_digitally_calibrated_comparator":True,
      "not_random_fabrication_mismatch":True}
    try:
        LINK.BITS=BITS
        bits=OFFSET.prbs31(BITS,0x54C4EE17)
        runner.run(deck(bits,alpha,gm),label)
        rows=LINK.read(work/"pll_driven_rx_wave.csv")
        sample,orig=LINK.evaluate(rows,bits,LINK.START_DATA_NS)
        score=OFFSET.score(sample,bits)
        stats=statistics(work/"rx_auto_ref_wave.csv",LINK.START_DATA_NS,
             LINK.START_DATA_NS+BITS*TX.UI_PS*1e-3)
        pll=LINK.frequency(rows)
        result.update({"status":"simulated","physical_ref":stats,
                       "postrun_holdout":score,
                       "PLL":pll,"unadjusted_score":orig})
        with (out/(label+"_MOS_latches.csv")).open("w",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(sample[0]))
            w.writeheader();w.writerows(sample)
    except Exception as e:
        result.update({"status":"simulator_or_scoring_failed",
                       "error":f"{type(e).__name__}: {str(e)[-1500:]}"})
    finally:
        LINK.BITS=old
    (out/(label+".json")).write_text(json.dumps(result,indent=2)+"\n")
    h=result.get("postrun_holdout",{}).get("holdout",{})
    print(f"AUTO_MOS_RX_OFFSET alpha={alpha} gm={gm} "
          f"status={result['status']} "
          f"VREF_mV={result.get('physical_ref',{}).get('during_last_data_reference_mV')} "
          f"gate_V={result.get('physical_ref',{}).get('during_last_data_gate_V')} "
          f"heldout_errors={h.get('invalid_or_wrong_UI')}/{h.get('expected_unique_bits')} "
          f"missing={h.get('missing_UI')} wrong={h.get('wrong_regenerated_UI')}",
          flush=True)
    return result

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--alpha",type=float,choices=ALPHAS,required=True)
    p.add_argument("--gm",type=float,choices=GMS,required=True)
    p.add_argument("--out",type=Path,default=Path("results/spice/p3_auto_MOS_RX_offset"))
    a=p.parse_args()
    main(a.out,a.alpha,a.gm)
