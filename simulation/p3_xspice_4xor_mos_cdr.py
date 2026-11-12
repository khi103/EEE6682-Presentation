#!/usr/bin/env python3
"""Mixed-mode XSPICE four-XOR data-phase detector with real MOS phase actuator.

Same ngspice transient includes:
  DB HiTek 180nm 8:4:2:1 MOS TX -> RC2 surrogate channel ->
  two real MOS regenerative RX latches,
  actual switched-MOS CP / 3-stage VCO / 450MHz reference XSPICE PFD/4,
  two-stage current-starved MOS receiver clock-delay actuator,
  NEW XSPICE digital D flip-flop data/edge samplers and FOUR d_xor gates.
XSPICE ADC bridges convert the received analogue voltage and MOS clock
phases to digital node signals. The four XOR comparator results are
converted via DAC bridges into a signed current that acts on a physical
2pF MOS-delay control capacitor. There is NO external PRBS label in the
phase detector.

IMPORTANT: This independently synthesized experimental digital phase
detector is NOT the full original Wong Fig19 circuit (E/D clock alignment,
exact demux and seven-bit saturating counter remain unimplemented).
The external 450MHz reference PLL still determines clock frequency;
digital phase loop does NOT contain its own physical switched MOS pump.
Do not claim data-CDR lock unless holdout errors, cycle coverage and
phase-controller settling independently pass. Failure is a valid result.
"""
from __future__ import annotations
import argparse,csv,json,math,shutil,sys
from pathlib import Path

import p3_transistor_driver as TX
import p3_reference_pll_integrated_mos_link as LINK
import p3_mos_physical_phase_delay as DELAY
import p3_live_mos_phase_servo as SERVO

BITS=256
PRBS_SEED=0x54C4EE17
SHIFTS=(-.05,.95)
GAINS_UA=(-20.,0.,20.,100.)
START_BIAS=1.1
CCTRL=2e-12

def prbs31(n,seed=PRBS_SEED):
    m=(1<<31)-1;x=seed&m
    out=[]
    for _ in range(n):
        out.append(x&1)
        x=((x<<1)&m)|(((x>>30)^(x>>27))&1)
    return out

def make_deck(bits,gain,shift):
    deck,start=DELAY.build(bits,START_BIAS,shift)
    source=f"VPDNB pd_nb 0 DC {START_BIAS:.6f}"
    sink=f"VPDPB pd_pb 0 DC {1.8-START_BIAS:.6f}"
    if deck.count(source)!=1 or deck.count(sink)!=1:raise RuntimeError("MOS delay control nodes not recognized")
    deck=deck.replace(source,"BNB_PD pd_nb 0 V={min(max(v(pdctrl),.65),1.65)}")
    deck=deck.replace(sink,"BPB_PD pd_pb 0 V={v(vdd)-v(pd_nb)}")
    digital=[
      "* Experimental XSPICE sampled 4-XOR phase discriminator (not original BBPD)",
      "* ADC RX comparator: an idealized threshold with 4mV transition uncertainty",
      "ABBRX [rx] [drx] adc_p3_rx",
      ".model adc_p3_rx adc_bridge(in_low=.248 in_high=.252)",
      "ABBCLK0 [clkeven clkodd n1 ph2] [dclke dclko dn1 dph2] adc_p3_clk",
      ".model adc_p3_clk adc_bridge(in_low=.8 in_high=1.0)",
      # Prototype edge/data clocks. The physical delayed ring provides two
      # staggered clock phases; the original Fig19 quarter-rate phases differ.
      "ADAT0 drx dclke dzero dzero dD0 dD0b sampled",
      "AEDGE0 drx dn1 dzero dzero dE0 dE0b sampled",
      "ADAT1 drx dclko dzero dzero dD1 dD1b sampled",
      "AEDGE1 drx dph2 dzero dzero dE1 dE1b sampled",
      ".model sampled d_dff(clk_delay=1e-11 set_delay=1e-11 reset_delay=1e-11 ic=2 rise_delay=1e-11 fall_delay=1e-11)",
      "AXORUP0 [dE0 dD0] du0 four_xor",
      "AXORDN0 [dD0 dE1] dd0 four_xor",
      "AXORUP1 [dE1 dD1] du1 four_xor",
      "AXORDN1 [dD1 dE0] dd1 four_xor",
      ".model four_xor d_xor(rise_delay=8e-12 fall_delay=8e-12 input_load=5e-15)",
      "ABBDAC4 [du0 dd0 du1 dd1] [vup0 vdn0 vup1 vdn1] xdac",
      "APROBE_DIGITAL [drx dclke dclko dn1 dph2 dD0 dD1 dE0 dE1] [vdrx vdclke vdclko vdn1probe vdph2 vD0 vD1 vE0 vE1] xdac",
      ".model xdac dac_bridge(out_low=0 out_high=1 out_undef=.5 input_load=5e-15 t_rise=5e-12 t_fall=5e-12)",
      # Physical integrating cap, behavioral CMOS gain amplifier/driver.
      f"VPDSET pdstart 0 {START_BIAS}",
      f"CPDLOOP pdctrl 0 {CCTRL:.10g} ic={START_BIAS}",
      "RPDLEAK pdctrl pdstart 200meg",
      f"BXORCHARGE pdctrl 0 I={{ {gain*1e-6:.10g} * "
      "(v(vdn0)+v(vdn1)-v(vup0)-v(vup1)) }}",
    ]
    deck=deck.replace(".control","\n".join(digital)+"\n.control",1)
    tail="quit\n.endc"
    if deck.count(tail)!=1:raise RuntimeError("Wrong control block")
    deck=deck.replace(tail,
      "wrdata xor_phase_details.csv time v(pdctrl) v(vup0) v(vdn0) v(vup1) v(vdn1) v(rx)\n"
      "wrdata xor_digital_inputs.csv time v(vdrx) v(vdclke) v(vdclko) v(vdn1probe) v(vdph2) v(vD0) v(vD1) v(vE0) v(vE1)\nquit\n.endc",1)
    return deck,start

def analyze_logic(path,start_ns,out_path):
    """Inspect four-XOR DAC outputs and the real MOS delay-control node."""
    records=[]
    for line in path.read_text().splitlines():
        try:
            a=[float(x) for x in line.split()]
        except ValueError:continue
        if len(a)>=14 and all(math.isfinite(x) for x in a):
            records.append({"time_s":a[0],"delay_control_V":a[3],
              "up0":a[5],"dn0":a[7],"up1":a[9],"dn1":a[11],"RX_V":a[13]})
    if len(records)<100:raise RuntimeError("Missing four-XOR diagnostic trace")
    with out_path.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(records[0]))
        w.writeheader()
        w.writerows(records[::max(1,len(records)//4000)])
    active=[x for x in records if x["time_s"]>=start_ns*1e-9]
    diffs=[x["dn0"]+x["dn1"]-x["up0"]-x["up1"] for x in active]
    ctrl=[x["delay_control_V"] for x in active]
    return {
      "post_data_samples":len(active),
      "mean_signed_UP_DOWN":sum(diffs)/len(diffs) if diffs else None,
      "peak_abs_UP_DOWN":max(abs(x) for x in diffs) if diffs else None,
      "nonzero_difference_fraction":sum(abs(x)>.10 for x in diffs)/len(diffs) if diffs else None,
      "control_min_V":min(ctrl) if ctrl else None,
      "control_max_V":max(ctrl) if ctrl else None,
      "control_end_V":ctrl[-1] if ctrl else None}

def analyze_digital_stages(path,start_ns,out_path):
    """0.5V means XSPICE U; locate first ADC/DFF stage stuck undefined."""
    fields=["RX_adc","clkeven_adc","clkodd_adc","ring_adc","delay_adc",
            "D0_dff","D1_dff","E0_dff","E1_dff"]
    stream=[]
    for line in path.read_text().splitlines():
        try:a=[float(x) for x in line.split()]
        except ValueError:continue
        if len(a)>=20 and all(math.isfinite(x) for x in a):
            stream.append({"time_s":a[0],**{k:a[3+2*i] for i,k in enumerate(fields)}})
    if len(stream)<100:raise RuntimeError("No raw digital diagnostic bridge")
    active=[x for x in stream if x["time_s"]>=start_ns*1e-9]
    if not active:raise RuntimeError("No digital samples after RX input data")
    summary={}
    for key in fields:
        vals=[x[key] for x in active]
        summary[key]={
            "minimum_V":min(vals),"maximum_V":max(vals),
            "fraction_low_0V":sum(v<.1 for v in vals)/len(vals),
            "fraction_high_1V":sum(v>.9 for v in vals)/len(vals),
            "fraction_unknown_0p5V":sum(.4<v<.6 for v in vals)/len(vals)}
    with out_path.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(stream[0]))
        w.writeheader();w.writerows(active[::max(1,len(active)//3500)])
    return summary

def main(out,gain,shift):
    if gain not in GAINS_UA or shift not in SHIFTS:raise ValueError("Preset unsupported")
    out.mkdir(parents=True,exist_ok=True)
    label=f"xor4_gain_{gain:+.0f}_phase_{shift:+.2f}".replace("+","p").replace("-","m").replace(".","p")
    work=TX.ENGINE_DIR/("p3_full_XSPICE_four_XOR_"+label)
    engine=TX.SpiceRunner(work)
    model=TX.model_path("tt")
    dst=work/model.name
    if not dst.exists() or model.stat().st_mtime>dst.stat().st_mtime:
        shutil.copy2(model,dst)
    bits=prbs31(BITS)
    result={
      "input_pattern":"256-bit PRBS31",
      "four_XSPICE_XOR_gates_present":True,
      "transistor_level_RX_figure19_recreated":False,
      "four_sampler_clock_alignment_original":False,
      "full_binary_7bit_phase_counter":False,
      "MOS_TX_RX_VCO_clock_actuator":True,
      "digital_phase_controller_behavioral_or_mixed_signal":True,
      "actual_2004_PLL_CDR_equivalent":False,
      "gain_uA":gain,"input_timing_offset_UI":shift,
    }
    try:
        deck,start=make_deck(bits,gain,shift)
        engine.run(deck,label)
        wave=LINK.read(work/"pll_driven_rx_wave.csv")
        # Always preserve actual analog + bridge diagnostics, including
        # when the RX sampler produces NO usable decision timestamps.
        logic=analyze_logic(work/"xor_phase_details.csv",start,out/(label+"_logic_wave.csv"))
        logic_stages=analyze_digital_stages(work/"xor_digital_inputs.csv",start,out/(label+"_digital_states.csv"))
        result["four_XOR_logic_diagnostics"]=logic
        result["digital_ADC_DFF_stage_diagnostics"]=logic_stages
        from bisect import bisect_left
        data_t=start*1e-9
        result["raw_clock_edges_after_data_start"]={
          "vco_rising":len(LINK.rising(wave,"vco_V",data_t)),
          "clk_even_falling":len(LINK.falling(wave,"clkeven_V",data_t)),
          "clk_odd_falling":len(LINK.falling(wave,"clkodd_V",data_t)),
        }
        focus=[r for r in wave if r["time_s"]>=data_t-1e-9]
        if focus:
            with (out/(label+"_analog_RX_and_clocks.csv")).open("w",newline="") as f:
                w=csv.DictWriter(f,fieldnames=list(focus[0]))
                w.writeheader()
                w.writerows(focus[::max(1,len(focus)//5000)])
        samples,orig=LINK.evaluate(wave,bits,start)
        held=SERVO.score_holdout(samples,bits,start)
        pll=LINK.frequency(wave)
        result.update({
          "status":"electrical_run",
          "reference_PLL":pll,
          "MOS_receiver_initial_score":orig,
          "heldout_coverage":held,
          "reference_PLL_near_1p8GHz":abs(pll["vco_GHz"]-1.8)<.025,
          "four_XOR_logic_diagnostics":logic,
          "digital_ADC_DFF_stage_diagnostics":logic_stages,
        })
        with (out/(label+"_physical_MOS_decisions.csv")).open("w",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(samples[0]))
            w.writeheader();w.writerows(samples)
    except Exception as e:
        result.update({"status":"SPICE_or_readout_failed",
                       "error":f"{type(e).__name__}: {str(e)[-2500:]}"})
    (out/(label+".json")).write_text(json.dumps(result,indent=2)+"\n")
    h=result.get("heldout_coverage",{}).get("holdout",{})
    print(f"XSPICE_4XOR_DATA_PHASE gain_uA={gain} shift={shift} "
          f"status={result['status']} "
          f"holdout_errors={h.get('total_invalid')}/{h.get('expected')} "
          f"wrong={h.get('wrong_regenerated')} "
          f"missed={h.get('missing')} "
          f"RXADC_U={result.get('digital_ADC_DFF_stage_diagnostics',{}).get('RX_adc',{}).get('fraction_unknown_0p5V')} "
          f"DFF0_U={result.get('digital_ADC_DFF_stage_diagnostics',{}).get('D0_dff',{}).get('fraction_unknown_0p5V')} "
          f"VCO_GHz={result.get('reference_PLL',{}).get('vco_GHz')}",flush=True)
    return result

if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("--gain",type=float,choices=GAINS_UA,required=True)
    a.add_argument("--shift",type=float,choices=SHIFTS,required=True)
    a.add_argument("--out",type=Path,default=Path("results/spice/p3_xspice_4xor_MOS_CDR"))
    args=a.parse_args()
    main(args.out,args.gain,args.shift)
