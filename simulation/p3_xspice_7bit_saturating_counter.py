#!/usr/bin/env python3
"""PDK-free seven-bit saturating up/down counter XSPICE d_state experiment.

XSPICE d_state has no silicon foundry dependency and is documented as
a programmable digital state machine. Generate ALL 128 states and
their four combinations of UP/DOWN votes using the explicit update law:
  UP=0 DN=0: hold
  UP=1 DN=0: min(127, count+1)
  UP=0 DN=1: max(0, count-1)
  UP=1 DN=1: hold (collision cancels).
This is a structural *candidate* for P3 Fig19-style saturating counter,
NOT a reconstructed transistor-level circuit and NOT an actual
serial-data-to-clock closed loop.

The truth table, transitions, and XSPICE realization are checked
separately, including complete saturation at 127 and floor at zero.
"""
from __future__ import annotations
import argparse,json,math,subprocess
from pathlib import Path

MAX=127
CLOCK_PERIOD_NS=2.
TEST_NS=600.

def update(q,up,down):
    if up==down:return q
    if up:return min(MAX,q+1)
    return max(0,q-1)

def generate_table(path):
    lines=["* Generated 7-bit saturating UP/DOWN state machine",
           "* Input bit order: UP=port0, DN=port1; output bit0 = LSB"]
    for q in range(128):
        output=" ".join(("1s" if q & (1<<i) else "0s") for i in range(7))
        transitions=[]
        for up,dn in ((0,0),(0,1),(1,0),(1,1)):
            transitions.append((f"{up} {dn}",update(q,up,dn)))
        for index,(vote,dest) in enumerate(transitions):
            if index==0:
                lines.append(f"{q} {output} {vote} -> {dest}")
            else:
                lines.append(f"{vote} -> {dest}")
    path.write_text("\n".join(lines)+"\n")
    assert len(lines)==2+128*4
    return len(lines)

def generate_circuit(path,table_name):
    lines=[
      "* PDK-free XSPICE 7bit saturating up/down phase counter",
      "VUP up 0 PWL(0n 0 2n 0 2.1n 1.8 280n 1.8 280.1n 0 600n 0)",
      "VDN dn 0 PWL(0n 0 290n 0 290.1n 1.8 570n 1.8 570.1n 0 600n 0)",
      "VCLK clk 0 PULSE(0 1.8 1n 5p 5p .9n 2n)",
      "VRESET reset 0 0",
      "AADC [up dn clk reset] [dup ddn dclk drst] pdadc",
      ".model pdadc adc_bridge(in_low=.8 in_high=1.0)",
      "ASTATE7 [dup ddn] dclk drst [dq0 dq1 dq2 dq3 dq4 dq5 dq6] p3count",
      f'.model p3count d_state(state_file="{table_name}" reset_state=0 clk_delay=1e-11 reset_delay=1e-11)',
      "ADAC7 [dq0 dq1 dq2 dq3 dq4 dq5 dq6] [vq0 vq1 vq2 vq3 vq4 vq5 vq6] pdac",
      ".model pdac dac_bridge(out_low=0 out_high=1 out_undef=.5 input_load=5e-15 t_rise=5e-12 t_fall=5e-12)",
      ".control","set noaskquit",
      "tran 20p 600n",
      "wrdata counter.csv time v(up) v(dn) v(clk) v(vq0) v(vq1) v(vq2) v(vq3) v(vq4) v(vq5) v(vq6)",
      "quit",".endc",".end",
    ]
    path.write_text("\n".join(lines)+"\n")

def read(path):
    vals=[]
    for line in path.read_text().splitlines():
        try:v=[float(x) for x in line.split()]
        except ValueError:continue
        if len(v)>=22 and all(math.isfinite(x) for x in v):
            binary=v[9::2][:7]
            unknown=sum(.30 < x < .70 for x in binary)
            value=sum((1<<i) for i,x in enumerate(binary) if x>.8)
            vals.append((v[0],value,unknown))
    if len(vals)<100:raise RuntimeError(f"Missing d_state counter waveform: {len(vals)}")
    return vals

def main(out):
    out.mkdir(parents=True,exist_ok=True)
    table=out/"saturating_counter.state"
    circuit=out/"saturating_counter.cir"
    generate_table(table)
    generate_circuit(circuit,table.name)
    # Check 128x4 state transitions independently from the ngspice deck.
    theoretical=[]
    for q in range(128):
      for up in (0,1):
       for dn in (0,1):
        y=update(q,up,dn)
        assert 0<=y<=127
        if (q==127 and up==1 and dn==0):assert y==127
        if (q==0 and dn==1 and up==0):assert y==0
        theoretical.append(y)
    run=subprocess.run(["ngspice","-b",circuit.name],cwd=out,
                       capture_output=True,text=True,timeout=120)
    (out/"ngspice_output.txt").write_text(run.stdout+"\n"+run.stderr)
    if (run.returncode!=0 or "D_STATE: state file was not read successfully." in (run.stdout+run.stderr) or "\nERROR\n" in (run.stdout+run.stderr)):
        raise RuntimeError(f"ngspice failed: {run.stderr[-2200:]} {run.stdout[-1600:]}")
    results=read(out/"counter.csv")
    before=[x for x in results if x[0]<2e-9]
    above=[x for x in results if 280e-9<x[0]<290e-9]
    final=[x for x in results if 580e-9<x[0]<600e-9]
    unknown=sum(x[2]>0 for x in results if x[0]>10e-9)
    # Transient U within nanosecond clock-edge events is expected in a
    # multi-bit asynchronous-bridge observation. Qualify the held state
    # 0.2ns after each actual DFF sample clock instead of at transitions.
    import bisect
    times=[x[0] for x in results]
    stable=[]
    for i in range(299):
        t=(1.2+2*i)*1e-9
        k=bisect.bisect_left(times,t)
        if k<len(results):stable.append(results[k])
    stable_U=sum(x[2]>0 for x in stable)
    summary={
      "status":"PDK-free actual ngspice d_state seven-bit counter executed",
      "states":128,"theoretical_state_transitions_checked":len(theoretical),
      "before_count":before[-1][1] if before else None,
      "after_ups_count":above[len(above)//2][1] if above else None,
      "final_count":final[len(final)//2][1] if final else None,
      "maximum_decoded_state":max(x[1] for x in results),
      "minimum_decoded_state":min(x[1] for x in results),
      "digital_unknown_waveform_rows":unknown,
      "samples_after_clock_settling":len(stable),
      "unknown_at_settled_clock_samples":stable_U,
      "transient_unknown_codes_may_occur_during_bridge_switches":True,
      "counter_saturation_127_reached":any(x[1]==127 for x in above),
      "counter_floor_zero_reached":any(x[1]==0 for x in final),
      "model_2004_exact_counter":False,
      "physical_closed_loop_MOS_CDR":False,
    }
    (out/"counter_summary.json").write_text(json.dumps(summary,indent=2)+"\n")
    print(f"XSPICE_7BIT_COUNTER max={summary['maximum_decoded_state']} "
          f"after_up={summary['after_ups_count']} "
          f"last={summary['final_count']} U_rows={unknown} stable_U={stable_U}/{len(stable)} "
          f"sat={summary['counter_saturation_127_reached']} "
          f"floor={summary['counter_floor_zero_reached']}",flush=True)
    if not(summary["counter_saturation_127_reached"] and
           summary["counter_floor_zero_reached"] and stable_U==0):
        raise AssertionError("7-bit state machine did not realize both counter saturation boundaries")
    return summary

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--out",type=Path,default=Path("results/digital/p3_XSPICE_7bit_saturating_counter"))
    main(p.parse_args().out)
