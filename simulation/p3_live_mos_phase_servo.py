#!/usr/bin/env python3
"""Exploratory live-data feedback into a REAL 180nm MOS clock phase actuator.

Full SAME ngspice transient:
 - MOS segmented 3.6Gb/s FFE TX and RC2 surrogate link
 - XSPICE 450MHz reference PFD/4 -> switched MOS charge pump -> physical
   MOS 3-stage ring VCO with reference PLL closed
 - Two current-starved MOS inverter clock-delay stages -> MOS RX latches
 - A separate analog RC integrator biasing the MOS clock-delay stages,
   driven by an ANALOG ngspice B-source RX-transition phase discriminator.

No transmitted labels, saved bit patterns or postrun phase search can
affect the physical phase control. A PRBS is only used AFTER SPICE for
fixed-lag sample scoring. This is a BEHAVIORAL data phase detector,
not Wong et al. Fig19 four-XOR transistor/digital BBPD.

The control is not guaranteed to converge: record both successful and
failed cases without declaring CDR lock from reference PLL frequency.
"""
from __future__ import annotations
import argparse,csv,json,math,shutil
from collections import defaultdict
from pathlib import Path
import p3_transistor_driver as TX
import p3_reference_pll_integrated_mos_link as LINK
import p3_mos_physical_phase_delay as DELAY

GAINS_UA=(-200.,-80.,0.,80.,200.,400.)
SHIFTS=(-.35,.35)
INIT=1.1
C_F=.8e-12
TRAIN=(18,90)
TEST=(90,246)

def generate(bits,gain_uA,shift,initial_bias=INIT):
    deck,start_ns=DELAY.build(bits,initial_bias,shift)
    oldn=f"VPDNB pd_nb 0 DC {initial_bias:.6f}"
    oldp=f"VPDPB pd_pb 0 DC {1.8-initial_bias:.6f}"
    assert deck.count(oldn)==1 and deck.count(oldp)==1
    deck=deck.replace(oldn,"BNB_PD pd_nb 0 V={min(max(v(pdctrl),.65),1.65)}")
    deck=deck.replace(oldp,"BPB_PD pd_pb 0 V={1.8-v(pd_nb)}")
    extra=[
      "* Physical MOS clock-delay feedback actuator; behavioral phase discriminator",
      f"VPDSET pdstart 0 DC {initial_bias:.9f}",
      f"CPDLOOP pdctrl 0 {C_F:.9g} ic={initial_bias:.9f}",
      "RPDLEAK pdctrl pdstart 200meg",
      "RRXEDGE rx rxdel 2k",
      "CRXEDGE rxdel 0 6f",
      "RCLKDEL clkeven clkdel 2k",
      "CCLKDEL clkdel 0 6f",
      # Analogue edge window of RX waveform, not true transmitted labels.
      "BRXEDGE rxedge 0 V={exp(-((v(rx)-.25)/.020)^2)*"
         "(tanh(100*(v(rx)-v(rxdel)))^2)}",
      # Phase error polarity relative to ACTUAL delayed physical MOS clock.
      "BPHASE phaseerr 0 V={tanh(8*(v(clkeven)-.9))*"
         "tanh(12*(v(clkeven)-v(clkdel)))}",
      f"BCDRPD pdctrl 0 I={{ {gain_uA*1e-6:.10g} *v(rxedge)*v(phaseerr) }}",
    ]
    deck=deck.replace(".control","\n".join(extra)+"\n.control",1)
    original="quit\n.endc"
    assert deck.count(original)==1
    deck=deck.replace(original,
       "wrdata pd_servo_diagnostics.csv time v(pdctrl) v(pd_nb) "
       "v(clkeven) v(rxedge) v(phaseerr)\nquit\n.endc",1)
    return deck,start_ns

def simple_feedback_trace(path):
    rec=[]
    for line in path.read_text().splitlines():
        try:v=[float(z) for z in line.split()]
        except ValueError:continue
        if len(v)>=12 and all(math.isfinite(z) for z in v):
            rec.append({"time_s":v[0],"controller_V":v[3],
                "actual_NMOS_gate_V":v[5],"clock_V":v[7],
                "RX_edge_analog_V":v[9],"phase_detector_V":v[11]})
    if len(rec)<1000:raise RuntimeError("No physical phase-control record")
    return rec

def score_segment(samples,bits,start_ns,lag,first,last):
    ui=TX.UI_PS*1e-12
    t0=start_ns*1e-9
    by_bit=defaultdict(list)
    for s in samples:
        i=math.floor((s["physical_clock_sample_s"]-t0)/ui)+lag
        if first<=i<last:by_bit[i].append(s)
    missing=unresolved=wrong=duplicates=0
    for i in range(first,last):
        x=by_bit.get(i,[])
        if not x:
            missing+=1
            continue
        duplicates+=max(0,len(x)-1)
        s=min(x,key=lambda k:k["physical_clock_sample_s"])
        if abs(s["Q_minus_QB_V"])<.15 or not s["regenerated"]:
            unresolved+=1
        elif int(s["Q_minus_QB_V"]>0)!=bits[i]:
            wrong+=1
    return {"expected":last-first,"missing":missing,
            "duplicates_extra":duplicates,
            "unresolved":unresolved,"wrong_regenerated":wrong,
            "total_invalid":missing+unresolved+wrong}

def score_holdout(samples,bits,start_ns):
    trials=[]
    for lag in range(-5,6):
        training=score_segment(samples,bits,start_ns,lag,*TRAIN)
        trials.append((training["total_invalid"],training["missing"],abs(lag),lag))
    chosen=min(trials)[-1]
    return {"common_train_selected_integer_frame_lag":chosen,
            "training":score_segment(samples,bits,start_ns,chosen,*TRAIN),
            "holdout":score_segment(samples,bits,start_ns,chosen,*TEST),
            "assumption":"PRBS used only for POSTRUN integer frame alignment and scoring; never for detector"}

def main(out,gain,shift,seed="prbs7"):
    if gain not in GAINS_UA or shift not in SHIFTS:raise ValueError("Unknown sweep parameter")
    if seed!="prbs7":raise ValueError("Unsupported pattern")
    out.mkdir(parents=True,exist_ok=True)
    label=f"gain_{gain:+.0f}uA_shift_{shift:+.2f}UI".replace("+","p").replace("-","m").replace(".","p")
    work=TX.ENGINE_DIR/("p3_live_mos_phase_servo_"+label)
    runner=TX.SpiceRunner(work)
    src=TX.model_path("tt");copy=work/src.name
    if not copy.exists() or src.stat().st_mtime>copy.stat().st_mtime:
        shutil.copy2(src,copy)
    bits=TX.prbs7(DELAY.BITS)
    deck,start_ns=generate(bits,gain,shift)
    runner.run(deck,label)
    rows=LINK.read(work/"pll_driven_rx_wave.csv")
    control=simple_feedback_trace(work/"pd_servo_diagnostics.csv")
    samples,original=LINK.evaluate(rows,bits,start_ns)
    heldout=score_holdout(samples,bits,start_ns)
    pll=LINK.frequency(rows)
    t0=start_ns*1e-9
    t1=t0+DELAY.BITS*TX.UI_PS*1e-12
    pre=[r["controller_V"] for r in control if (t0-10e-9)<=r["time_s"]<t0]
    last=[r["controller_V"] for r in control if (t1-12e-9)<=r["time_s"]<=t1]
    bias0=sum(pre)/len(pre) if pre else None
    bias1=sum(last)/len(last) if last else None
    result={
      "case":label,"data_start_shift_UI":shift,"gain_microamp":gain,
      "transistor_MOS_clock_delay":True,
      "actual_in_spice_closed_data_phase_feedback":gain!=0,
      "phase_detector_type":"ngspice behavioral RX analog threshold and MOS clock edge",
      "clock_generation":"450MHz reference PLL, real MOS charge-pump/VCO + real MOS starved delay stages",
      "VCO":pll,"postrun_original":original,"coverage_aware":heldout,
      "actuator_start_ctrl_V":bias0,
      "actuator_last_ctrl_V":bias1,
      "actuator_drift_mV":(bias1-bias0)*1e3 if bias0 is not None and bias1 is not None else None,
      "charge_pump_to_delay_mapping_is_transistor_simulated":True,
      "actual_Fig19_four_XOR_BBPD":False,
      "claims_physical_CDR_lock":False,
      "statistical_BER_established":False,
    }
    (out/(label+".json")).write_text(json.dumps(result,indent=2)+"\n")
    # Raw control trace independent of postrun scoring: preserve 5k points.
    with (out/(label+"_MOS_ctrl.csv")).open("w",newline="") as f:
        keys=list(control[0])
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader()
        w.writerows(control[::max(1,len(control)//5000)])
    print(f"DATA_TO_PHYSICAL_MOS_PHASE gain_uA={gain:+.0f} shift_UI={shift:+.2f} "
          f"VCO={pll['vco_GHz']:.9f}GHz "
          f"controller_start={bias0} controller_end={bias1} "
          f"heldout_errors={heldout['holdout']['total_invalid']}/{heldout['holdout']['expected']} "
          f"missing={heldout['holdout']['missing']} "
          f"wrong={heldout['holdout']['wrong_regenerated']} "
          f"unresolved={heldout['holdout']['unresolved']}",flush=True)
    return result

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--gain",type=float,choices=GAINS_UA,required=True)
    p.add_argument("--shift",type=float,choices=SHIFTS,required=True)
    p.add_argument("--out",type=Path,default=Path("results/spice/p3_live_MOS_phase_servo"))
    a=p.parse_args()
    main(a.out,a.gain,a.shift)
