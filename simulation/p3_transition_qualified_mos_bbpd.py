#!/usr/bin/env python3
"""Experimental transition-qualified Alexander BBPD with actual MOS clocks.

A single ngspice transient electrically includes:
  - 3.6Gb/s binary-weighted DB HiTek 180nm MOS transmitter
  - ideal buffered two-pole RC surrogate channel
  - two transistor-level regenerative MOS receiver latches
  - 450MHz XSPICE reference PFD /4 -> switched MOS charge pump and VCO
  - two actual current-starved MOS CMOS stages for RX clock phase
  - XSPICE digital DFF samplers driven by *physical* MOS clock signals
  - three XOR + two AND gates for a TRANSITION-QUALIFIED Alexander PD
  - XSPICE DAC and analog current feeding a physical MOS phase-delay C

This is an independent hybrid mixed-signal prototype. It is NOT the
paper's exact four-XOR half-rate architecture: the clock phases and
saturation counter were not reconstructed. The phase detector does
NOT see true PRBS labels. The RX data is sampled from the simulated
MOS/RC waveform. Use 'data CDR lock' only after separate successful
phase and data-bit qualification, not merely reference PLL lock.
"""
from __future__ import annotations
import argparse,csv,json,math,shutil
from pathlib import Path
import p3_transistor_driver as TX
import p3_reference_pll_integrated_mos_link as LINK
import p3_mos_physical_phase_delay as PHASE
import p3_live_mos_phase_servo as SCORING

BITS=256
SEED=0x54C4EE17
SHIFT=(-.05,.95)
GAINS_UA=(-80.,-20.,0.,20.,80.)
CONTROL_C=40e-12
INIT_CTRL=1.10
VREF_RX=.25

def prbs31(n):
    state=SEED & ((1<<31)-1);mask=(1<<31)-1
    if not state:raise ValueError("Bad seed")
    result=[]
    for _ in range(n):
        result.append(state&1)
        state=((state<<1)&mask)|(((state>>30)^(state>>27))&1)
    return result

def truth_table():
    """Static proof of the signed Alexander transition detector."""
    data=[]
    for left in (0,1):
      for edge in (0,1):
       for right in (0,1):
        transition=left^right
        up=(left^edge)&transition
        down=(edge^right)&transition
        if transition==0 and (up or down):
            raise AssertionError("Non-transition caused early/late vote")
        if transition==1 and (up+down)!=1:
            raise AssertionError("Transition must yield exactly one vote")
        data.append({
           "previous_data":left,"edge_data":edge,"next_data":right,
           "transition":transition,"UP":up,"DN":down,
           "charge_vote":down-up})
    return data

def circuit(bits,gain,shift):
    deck,start=PHASE.build(bits,INIT_CTRL,shift)
    src=f"VPDNB pd_nb 0 DC {INIT_CTRL:.6f}"
    snk=f"VPDPB pd_pb 0 DC {1.8-INIT_CTRL:.6f}"
    if deck.count(src)!=1 or deck.count(snk)!=1:
        raise RuntimeError("Original real MOS phase actuator not recognized")
    deck=deck.replace(src,"BNB_PD pd_nb 0 V={min(max(v(pdctrl),.65),1.65)}",1)
    deck=deck.replace(snk,"BPB_PD pd_pb 0 V={v(vdd)-v(pd_nb)}",1)
    lines=[
        "* Physical MOS clocks, transition qualified Alexander DFF+XOR+AND",
        "AADC_RX [rx] [drx] adc_data",
        ".model adc_data adc_bridge(in_low=.249 in_high=.251)",
        "AADC_CLK [n1 clkodd clkeven] [dclk0 dclkedge dclk1] adc_clock",
        ".model adc_clock adc_bridge(in_low=.8 in_high=1.0)",
        # Each half-rate VCO period spans two 3.6Gb/s UI.
        # n1 rises then clkodd rises ~one-half UI later then clkeven
        # rises around the next UI: actual phase must be verified.
        "ADFF0 drx dclk0 dzero dzero dleft dleftb p3_dff",
        "ADFFE drx dclkedge dzero dzero dedge dedgeb p3_dff",
        "ADFF1 drx dclk1 dzero dzero dright drightb p3_dff",
        ".model p3_dff d_dff(clk_delay=1e-11 set_delay=1e-11 reset_delay=1e-11 ic=2 rise_delay=1e-11 fall_delay=1e-11)",
        "AXOR_TRANS [dleft dright] dtrans p3xor",
        "AXOR_UP [dleft dedge] dxup p3xor",
        "AXOR_DN [dedge dright] dxdn p3xor",
        ".model p3xor d_xor(rise_delay=8e-12 fall_delay=8e-12 input_load=5e-15)",
        "AAND_UP [dxup dtrans] dup p3and",
        "AAND_DN [dxdn dtrans] ddn p3and",
        ".model p3and d_and(rise_delay=8e-12 fall_delay=8e-12 input_load=5e-15)",
        "ADAC_UPDN [dup ddn] [vup vdn] p3_dac",
        ".model p3_dac dac_bridge(out_low=0 out_high=1 out_undef=.5 input_load=5e-15 t_rise=5e-12 t_fall=5e-12)",
        "ADAC_DBG [dleft dedge dright dtrans] [vleft vedge vright vtrans] p3_dac",
        f"VSTART_PHASE startpd 0 {INIT_CTRL:.6f}",
        f"CPHASE_CTRL pdctrl 0 {CONTROL_C:.10g} ic={INIT_CTRL:.6f}",
        "RPHASE_LEAK pdctrl startpd 200meg",
        # The late data DFF is clocked on clkeven rising. Only charge
        # while clkeven is high, after all 3 data sample registers
        # have received the current half-rate unit's samples.
        f"BDATA_FEEDBACK pdctrl 0 I={{ {gain*1e-6:.10g}*"
           "(v(vdn)-v(vup))*(.5+.5*tanh(8*(v(clkeven)-.9))) }",
    ]
    deck=deck.replace(".control","\n".join(lines)+"\n.control",1)
    original="quit\n.endc"
    if deck.count(original)!=1:raise ValueError("Unrecognized SPICE .control")
    deck=deck.replace(original,
        "wrdata p3_alexander_pd.csv time v(pdctrl) v(vup) v(vdn) "
        "v(vleft) v(vedge) v(vright) v(vtrans) v(rx) v(clkeven)\n"
        "quit\n.endc",1)
    return deck,start

def parse_pd(path,start_ns):
    records=[]
    for line in path.read_text().splitlines():
        try:v=[float(x) for x in line.split()]
        except ValueError:continue
        if len(v)>=20 and all(math.isfinite(x) for x in v):
            records.append({"time_s":v[0],
               "physical_gate_control_V":v[3],"up_V":v[5],"down_V":v[7],
               "previous_data_V":v[9],"edge_sample_V":v[11],
               "next_data_V":v[13],"transition_V":v[15],
               "actual_RX_V":v[17],"actual_clock_V":v[19]})
    if len(records)<500:raise RuntimeError("Missing phase-detector waveforms")
    r=[x for x in records if x["time_s"]>=start_ns*1e-9]
    if not r:raise RuntimeError("No phase detector records after data start")
    difference=[x["down_V"]-x["up_V"] for x in r]
    states=[x["physical_gate_control_V"] for x in r]
    return records,{
       "after_data_records":len(r),
       "transition_detected_fraction":sum(x["transition_V"]>.75 for x in r)/len(r),
       "UP_active_fraction":sum(x["up_V"]>.75 for x in r)/len(r),
       "DN_active_fraction":sum(x["down_V"]>.75 for x in r)/len(r),
       "difference_nonzero_fraction":sum(abs(d)>.5 for d in difference)/len(r),
       "difference_mean_V":sum(difference)/len(r),
       "control_start_V":r[0]["physical_gate_control_V"],
       "control_end_V":states[-1],
       "control_min_V":min(states),"control_max_V":max(states),
    }

def main(out,gain,shift):
    if gain not in GAINS_UA or shift not in SHIFT:raise ValueError
    out.mkdir(parents=True,exist_ok=True)
    label=f"gain_{gain:+.0f}_shift_{shift:+.2f}".replace("+","p").replace("-","m").replace(".","p")
    work=TX.ENGINE_DIR/("p3_alexander_pd_"+label)
    engine=TX.SpiceRunner(work)
    src=TX.model_path("tt");dst=work/src.name
    if not dst.exists() or src.stat().st_mtime>dst.stat().st_mtime:
        shutil.copy2(src,dst)
    bits=prbs31(BITS)
    result={
      "pattern":"PRBS31","pattern_seed":hex(SEED),
      "XSPICE_data_phase_detector":"3xor+2and transition-qualified Alexander prototype",
      "physical_analog_blocks":"DB HiTek MOS TX/RX/CP/VCO and MOS delay",
      "reference_PLL":"XSPICE ideal 450MHz divided PFD",
      "chip_Fig19_exact":False,
      "real_7bit_saturating_counter_in_data_loop":False,
      "loop_control_cap_F":CONTROL_C,
      "gain_uA":gain,"phase_shift_UI":shift,
      "truth_table_validated":len(truth_table())==8,
      "electrical_success":False,
      "data_CDR_lock_proven":False,
    }
    try:
        deck,start=circuit(bits,gain,shift)
        engine.run(deck,label)
        waves=LINK.read(work/"pll_driven_rx_wave.csv")
        pd,diagnostics=parse_pd(work/"p3_alexander_pd.csv",start)
        physical,initial=LINK.evaluate(waves,bits,start)
        audit=SCORING.score_holdout(physical,bits,start)
        pll=LINK.frequency(waves)
        result.update({
            "status":"simulation_completed",
            "electrical_success":True,
            "PD_activity":diagnostics,
            "reference_PLL":pll,
            "MOS_latch_original":initial,
            "coverage_aware_holdout":audit,
        })
        with (out/(label+"_PD.csv")).open("w",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(pd[0]));w.writeheader()
            w.writerows(pd[::max(1,len(pd)//6000)])
        with (out/(label+"_MOS_bits.csv")).open("w",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(physical[0]));w.writeheader()
            w.writerows(physical)
    except Exception as e:
        result.update({"status":"simulator_or_readout_failed",
                       "error":f"{type(e).__name__}: {str(e)[-2000:]}"})
    (out/(label+".json")).write_text(json.dumps(result,indent=2)+"\n")
    metric=result.get("coverage_aware_holdout",{}).get("holdout",{})
    pd=result.get("PD_activity",{})
    print(
       f"ALEXANDER_MOS_CDR gain_uA={gain} shift_UI={shift} "
       f"status={result['status']} "
       f"UP_frac={pd.get('UP_active_fraction')} DN_frac={pd.get('DN_active_fraction')} "
       f"PD_diff_frac={pd.get('difference_nonzero_fraction')} "
       f"controller_final_V={pd.get('control_end_V')} "
       f"holdout_error={metric.get('total_invalid')}/{metric.get('expected')} "
       f"wrong={metric.get('wrong_regenerated')} missing={metric.get('missing')}",
       flush=True)
    return result

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--gain",type=float,choices=GAINS_UA,required=True)
    p.add_argument("--shift",type=float,choices=SHIFT,required=True)
    p.add_argument("--out",type=Path,default=Path("results/spice/p3_transition_XSPICE_BBPD"))
    a=p.parse_args()
    main(a.out,a.gain,a.shift)
