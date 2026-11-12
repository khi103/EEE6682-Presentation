#!/usr/bin/env python3
"""Experimental 7-bit XSPICE digital-up/down phase loop with physical MOS RX.

ONE ngspice transient connects:
- DB HiTek 180nm 3.6Gb/s segmented transistor transmitter
- RC2 surrogate channel and transistor regenerative RX latches
- XSPICE digital 450MHz reference PFD /4 plus MOS charge pump and VCO
- two real MOS current-starved RX clock phase delay cells
- independently reconstructed four-XOR DFF receiver-data phase detector
- real XSPICE d_state 128-state SATURATING digital up/down counter
- seven XSPICE DAC outputs mapped through B-source bias drivers to
  actual CMOS delay-control MOS gates.

TX bit labels are NOT wired to the BBPD, counter or clock actuator.
They are used only after SPICE for post-run heldout decision scoring.

This is not the original 2004 Fig19 exact timing/counter architecture.
The reference PLL remains an ideal 450MHz XSPICE-controlled reference
PLL, and the digital counter's bit-DAC-to-analogue-phase gain remains
an ideal model. Full physical-data CDR lock must be demonstrated rather
than inferred from successful simulator execution.
"""
from __future__ import annotations
import argparse,csv,json,math,shutil
from pathlib import Path
import p3_transistor_driver as TX
import p3_xspice_4xor_mos_cdr as FOUR
import p3_reference_pll_integrated_mos_link as LINK
import p3_live_mos_phase_servo as SCORE
import p3_xspice_7bit_saturating_counter as COUNTER

SEEDS=(0x54C4EE17,0x13572468)
SHIFTS=(-.05,.95)
STEPS_MV=(-2.,0.,2.,4.)
BITS=256
CENTER=63

def make_deck(bits,shift,step_mv):
    deck,start_ns=FOUR.make_deck(bits,0.,shift)
    original="BNB_PD pd_nb 0 V={min(max(v(pdctrl),.65),1.65)}"
    if deck.count(original)!=1:raise RuntimeError("Expected exactly one physical MOS delay gate driver")
    volts="+".join(f"{2**i}*v(vcnt{i})" for i in range(7))
    # 0.0-1.8V digital-bit bridge encodes binary value.
    scalar=f"(({volts})/1.8 - {CENTER})"
    driver=f"BNB_COUNT pd_nb 0 V={{min(max(1.1+({step_mv*1e-3:.10g})*{scalar},.65),1.65)}}"
    deck=deck.replace(original,driver,1)
    # Counter starts centered, gated by external receiver packet enable:
    #   packet enable time is known to the testbench, never the data labels.
    additions=[
       "* 7-bit 128-state XSPICE digital counter driven by four-XOR data PD",
       "VCDREN cdrenable 0 PWL(0n 0 1219n 0 1220n 1.8 1400n 1.8)",
       "AADC_EN [cdrenable] [denable] aencount",
       ".model aencount adc_bridge(in_low=.8 in_high=1.0)",
       "AORUP [du0 du1] dcounter_up_raw xor_vote_or",
       "AORDN [xdn0 xdn1] dcounter_dn_raw xor_vote_or",
       ".model xor_vote_or d_or(rise_delay=8e-12 fall_delay=8e-12 input_load=5e-15)",
       "AANDUP [dcounter_up_raw denable] dcounter_up_enabled counter_gate_and",
       "AANDDN [dcounter_dn_raw denable] dcounter_dn_enabled counter_gate_and",
       ".model counter_gate_and d_and(rise_delay=8e-12 fall_delay=8e-12 input_load=5e-15)",
       "ADIV_COUNTER dclke dcount_clk counter_div2",
       ".model counter_div2 d_fdiv(div_factor=2 high_cycles=1 i_count=0 rise_delay=1e-11 fall_delay=1e-11)",
       "AUPDOWN7 [dcounter_up_enabled dcounter_dn_enabled] dcount_clk dzero "
       "[dcnt0 dcnt1 dcnt2 dcnt3 dcnt4 dcnt5 dcnt6] digital_phase_counter",
       '.model digital_phase_counter d_state(state_file="p3_saturating_counter.state" reset_state=63 clk_delay=1e-11 reset_delay=1e-11)',
       "A7BIT_DAC [dcnt0 dcnt1 dcnt2 dcnt3 dcnt4 dcnt5 dcnt6] "
       "[vcnt0 vcnt1 vcnt2 vcnt3 vcnt4 vcnt5 vcnt6] counter7_dac",
       ".model counter7_dac dac_bridge(out_low=0 out_high=1.8 out_undef=.9 input_load=5e-15 t_rise=8e-12 t_fall=8e-12)",
    ]
    deck=deck.replace(".control","\n".join(additions)+"\n.control",1)
    end="quit\n.endc"
    if deck.count(end)!=1:raise RuntimeError("SPICE control termination changed")
    deck=deck.replace(end,
       "wrdata physical_counter_control.csv time v(pd_nb) v(vcnt0) v(vcnt1) "
       "v(vcnt2) v(vcnt3) v(vcnt4) v(vcnt5) v(vcnt6) "
       "v(vup0) v(vdn0) v(rx)\nquit\n.endc",1)
    return deck,start_ns

def decoded_trajectory(path,start_ns,out_file):
    samples=[]
    for line in path.read_text().splitlines():
        try:a=[float(x) for x in line.split()]
        except ValueError:continue
        # time plus 11 printed node vectors -> 24 doubles.
        if len(a)>=24 and all(math.isfinite(x) for x in a):
            bit=[a[5+2*i] for i in range(7)]
            q=sum((1<<i) for i,b in enumerate(bit) if b>.9)
            unknown=sum(.4<b<1.35 for b in bit)
            samples.append({
              "time_s":a[0],"physical_delay_gate_V":a[3],
              "counter_q":q,"unknown_bits":unknown,
              "four_XOR_up_V":a[19],"four_XOR_dn_V":a[21],
              "rx_voltage_V":a[23]})
    if len(samples)<100:raise RuntimeError("No counter-control physical analog trace")
    after=[x for x in samples if x["time_s"]>=start_ns*1e-9]
    if not after:raise RuntimeError("Counter has no received-data trace")
    # Counter states are sampled exactly from DAC voltage values, where
    # bit transitions can briefly read undefined, never claim zero U.
    with out_file.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(samples[0]))
        w.writeheader()
        w.writerows(after[::max(1,len(after)//6000)])
    ctrl=[x["physical_delay_gate_V"] for x in after]
    return {
      "data_samples":len(after),"range_counter_min":min(x["counter_q"] for x in after),
      "range_counter_max":max(x["counter_q"] for x in after),
      "unknown_rows_during_switches":sum(x["unknown_bits"]>0 for x in after),
      "start_actual_MOS_phase_control_V":ctrl[0],
      "end_actual_MOS_phase_control_V":ctrl[-1],
      "actual_MOS_phase_control_delta_mV":(ctrl[-1]-ctrl[0])*1e3,
      "actual_MOS_phase_control_peak_to_peak_mV":(max(ctrl)-min(ctrl))*1e3,
    }

def run(out,seed,shift,step_mv):
    if seed not in SEEDS or shift not in SHIFTS or step_mv not in STEPS_MV:raise ValueError
    out.mkdir(parents=True,exist_ok=True)
    label=f"seed_{seed:X}_phase_{shift:+.2f}_step_{step_mv:+g}mV".replace("+","p").replace("-","m").replace(".","p")
    work=TX.ENGINE_DIR/("p3_physical_MOS_7bit_counter_"+label)
    engine=TX.SpiceRunner(work)
    model=TX.model_path("tt");copy=work/model.name
    if not copy.exists() or model.stat().st_mtime>copy.stat().st_mtime:shutil.copy2(model,copy)
    COUNTER.generate_table(work/"p3_saturating_counter.state")
    bits=FOUR.prbs31(BITS,seed=seed)
    r={
       "seed":hex(seed),"shift_UI":shift,"physical_phase_gain_mV_per_counter_code":step_mv,
       "actual_seven_bit_XSPICE_saturating_counter":True,
       "real_MOS_phase_delay_cells":True,
       "model_data_phase_detector":"independently reconstructed four-XOR BBPD",
       "real_PDK_MOS_TX_RX_CP_VCO":True,
       "physical_2004_P3_Fig19_same":False,
       "full_data_CDR_lock_proven":False,
       "PRBS_labels_used_for_in_SPICE_control":False,
    }
    try:
        d,start=make_deck(bits,shift,step_mv)
        engine.run(d,label)
        wave=LINK.read(work/"pll_driven_rx_wave.csv")
        pll=LINK.frequency(wave)
        mos,original=LINK.evaluate(wave,bits,start)
        h=SCORE.score_holdout(mos,bits,start)
        ctl=decoded_trajectory(work/"physical_counter_control.csv",start,
                               out/(label+"_counter_codes.csv"))
        r.update({
          "status":"simulated","reference_PLL":pll,
          "physical_RX_score":h,"original_decisions":original,
          "counter_and_MOS_actuation":ctl,
        })
        with (out/(label+"_MOS_bit_decisions.csv")).open("w",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(mos[0]))
            w.writeheader();w.writerows(mos)
    except Exception as exc:
        r.update({"status":"simulation_or_readout_failed",
                  "error":f"{type(exc).__name__}: {str(exc)[-2000:]}"})
    (out/(label+".json")).write_text(json.dumps(r,indent=2)+"\n")
    h=r.get("physical_RX_score",{}).get("holdout",{})
    ctl=r.get("counter_and_MOS_actuation",{})
    print(f"MOS_REAL_7BIT_DATA_COUNTER seed={hex(seed)} phase_UI={shift:+.2f} "
          f"step_mV={step_mv:+g} status={r['status']} "
          f"counter_span={ctl.get('range_counter_min')}..{ctl.get('range_counter_max')} "
          f"physical_MOS_gate_pp_mV={ctl.get('actual_MOS_phase_control_peak_to_peak_mV')} "
          f"VCO_GHz={r.get('reference_PLL',{}).get('vco_GHz')} "
          f"data_errors={h.get('total_invalid')}/{h.get('expected')} "
          f"missing={h.get('missing')} wrong={h.get('wrong_regenerated')}",flush=True)
    return r

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--seed",type=lambda s:int(s,0),choices=SEEDS,required=True)
    p.add_argument("--shift",type=float,choices=SHIFTS,required=True)
    p.add_argument("--step-mv",type=float,choices=STEPS_MV,required=True)
    p.add_argument("--out",type=Path,default=Path("results/spice/p3_real_7bit_MOS_data_counter"))
    a=p.parse_args()
    run(a.out,a.seed,a.shift,a.step_mv)
