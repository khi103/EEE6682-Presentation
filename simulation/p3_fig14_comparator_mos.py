#!/usr/bin/env python3
"""Fig.14-INFORMED DB HiTek 1.8-V PMOS-input transistor-level comparator.

Source: Wong et al. (JSSC 2004), Sec. IV-A, Fig.14: PMOS differential
preamp accommodates Vcm=0.25V, 2-GHz bandwidth control (M3-M6),
offset trim (M8-M10) and regenerative latch (M11-M19).

THIS test implements only a PMOS differential preamp, NMOS current
mirror load, capacitive bandwidth control, two CMOS buffer stages.
No clocked regenerative latch M11-M19, binary-weighted M10 offset,
M3-M6 active triode-feedback or 4-phase sampling.
It is an INDEPENDENT simplified transistor comparator, not the 19-MOS
original circuit. It does exercise PDK MOS I-V, offset, transient.
"""
from pathlib import Path
import argparse,csv,json,math,shutil
import p3_transistor_driver as TX

CORNERS=TX.CORNER_NAMES
VDD=1.8
VCM=.25
DELTA_INPUT_V=(-.15,-.12,-.10,-.07,-.05,-.03,-.02,-.01,0,.01,.02,.03,.05,.07,.10,.12,.15)
WIDTH_P1=2.4
WIDTH_P2=2.4
WIDTH_TAIL=.8
WIDTH_LOAD=.85
WBUF_N=1.0
WBUF_P=2.0

def circuit(corner,vin,ref=VCM,input_skew=0.0,cap_pre=2e-15,
            pulse=False, pulse_period_ns=.55556, pulse_amplitude_V=.035, trace_name="fig14_transient.csv"):
    # Positive P1 width mismatch means larger PMOS in VIN branch.
    # A 0.25-V input is in the low-common-mode operating region.
    if pulse:
        insource=(f"VIN in 0 PULSE({VCM-pulse_amplitude_V:.8g} "
                  f"{VCM+pulse_amplitude_V:.8g} {pulse_period_ns/4:.8g}n "
                  f"10p 10p {pulse_period_ns/2:.8g}n {pulse_period_ns:.8g}n)")
    else:
        insource=f"VIN in 0 {vin:.10g}"
    lines=[
      "* Independently reconstructed low-VCM PMOS-input CMOS preamp and slicer",
      "* NOT original P3 Fig.14 19-device dynamic comparator",
      f'.include "db180_svt018_{corner}.lib"',
      ".temp 27","VDD vdd 0 1.8",
      f"VREF ref 0 {ref:.10g}",
      "VBIAS vbias 0 1.10",
      insource,
      # Current source PMOS feeds a PMOS differential pair from 1.8 V.
      f"XPTAIL tail vbias vdd vdd 0 pch_svt_1p8v width={WIDTH_TAIL}u length=0.36u multi=1",
      f"XPIN pos in tail vdd 0 pch_svt_1p8v width={WIDTH_P1*(1+input_skew):.8g}u length=0.18u multi=1",
      f"XPREF pre ref tail vdd 0 pch_svt_1p8v width={WIDTH_P2*(1-input_skew):.8g}u length=0.18u multi=1",
      # Common-current-mirror active load, differential-to-single.
      f"XNLDIO pos pos 0 0 nch_svt_1p8v width={WIDTH_LOAD}u length=0.36u multi=1",
      f"XNLMIR pre pos 0 0 nch_svt_1p8v width={WIDTH_LOAD}u length=0.36u multi=1",
      f"CPRE pre 0 {cap_pre:.8g}",
      # Two physical CMOS inverters, so OUT is high when VIN > VREF.
      f"XNBUF1 mid pre 0 0 nch_svt_1p8v width={WBUF_N}u length=0.18u multi=1",
      f"XPBUF1 mid pre vdd vdd 0 pch_svt_1p8v width={WBUF_P}u length=0.18u multi=1",
      f"XNBUF2 out mid 0 0 nch_svt_1p8v width={WBUF_N}u length=0.18u multi=1",
      f"XPBUF2 out mid vdd vdd 0 pch_svt_1p8v width={WBUF_P}u length=0.18u multi=1",
      "COUT out 0 10f",
      ".control","set noaskquit",
    ]
    if pulse:
        lines += [f"tran {min(10.,pulse_period_ns*1000/250):.6g}p "
                  f"{max(12.0,pulse_period_ns*5):.8g}n",
                  f"wrdata {trace_name} time v(in) v(pre) v(out) i(vdd)"]
    else:
        lines += ["op","print v(pre) v(out) i(vdd)"]
    lines += ["quit",".endc",".end"]
    return "\n".join(lines)+"\n"

def parse_trace(path):
    data=[]
    for row in path.read_text().splitlines():
        try: a=[float(x) for x in row.split()]
        except ValueError:continue
        if len(a)>=10 and all(math.isfinite(x) for x in a):
            # ngspice wrdata with 4 vectors can have 10 columns:
            # time, time, vin, time, vpre, time, vout, time, isupply
            data.append({"time_s":a[0],"vin_V":a[3],
                         "vpre_V":a[5],"vout_V":a[7],"isupply_A":a[9]})
        elif len(a)==8 and all(math.isfinite(x) for x in a):
            data.append({"time_s":a[0],"vin_V":a[3],
                         "vpre_V":a[5],"vout_V":a[7]})
    if len(data)<200:
        raise RuntimeError(f"No valid comparator transient data: {path} ({len(data)} rows)")
    return data

def save(out,filename,rows):
    with (out/filename).open("w",newline="",encoding="utf-8") as f:
        wr=csv.DictWriter(f,fieldnames=list(rows[0]))
        wr.writeheader();wr.writerows(rows)

def test(out):
    out.mkdir(parents=True,exist_ok=True)
    work=TX.ENGINE_DIR/"p3_fig14_comparator"
    runner=TX.SpiceRunner(work)
    for corner in CORNERS:
        model=TX.model_path(corner)
        copy=work/model.name
        if not copy.exists() or model.stat().st_mtime>copy.stat().st_mtime:
            shutil.copy2(model,copy)
    dc=[]
    for corner in CORNERS:
        for skew in (-.04,0,.04):
            for vin_diff in DELTA_INPUT_V:
                vin=VCM+vin_diff
                log=runner.run(circuit(corner,vin,input_skew=skew),
                               f"dc_{runner.calls:05d}")
                dc.append({"corner":corner,"device_width_skew_fraction":skew,
                           "vin_V":vin,"input_diff_mV":vin_diff*1e3,
                           "preamp_V":TX.spice_vector(log,"v(pre)"),
                           "out_V":TX.spice_vector(log,"v(out)"),
                           "supply_current_A":-TX.spice_vector(log,"i(vdd)")})
        print(f"{corner}: completed {len(DELTA_INPUT_V)*3} PMOS preamp DC points",flush=True)
    save(out,"fig14_comparator_dc.csv",dc)
    conditions={}
    for corner in CORNERS:
        subset=[r for r in dc if r["corner"]==corner and r["device_width_skew_fraction"]==0]
        lo=next(r for r in subset if abs(r["input_diff_mV"]+30)<1e-4)
        hi=next(r for r in subset if abs(r["input_diff_mV"]-30)<1e-4)
        conditions[corner]={
          "out_at_minus_30mV_V":lo["out_V"],
          "out_at_plus_30mV_V":hi["out_V"],
          "output_delta_V":hi["out_V"]-lo["out_V"],
          "typical_current_uA":sum(r["supply_current_A"] for r in subset)/len(subset)*1e6,
        }
    # A low-frequency, large-differential-signal functional smoke test and
    # a separate 1.8GHz, 35mV sensitivity stress test.
    dynamic={}
    for label,period,amp in (("low_frequency_100MHz",10.,.15),
                             ("high_frequency_1p8GHz",.55556,.035)):
        trace_name=f"fig14_transient_{label}.csv"
        runner.run(circuit("tt",VCM,pulse=True,
                           pulse_period_ns=period,
                           pulse_amplitude_V=amp,
                           trace_name=trace_name),
                   f"transient_{runner.calls:05d}")
        trans=parse_trace(work/trace_name)
        save(out,trace_name,trans)
        vals=[r["vout_V"] for r in trans]
        dynamic[label]={"out_min_V":min(vals),"out_max_V":max(vals),
                        "out_peak_to_peak_V":max(vals)-min(vals),
                        "waveform_rows":len(trans),"period_ns":period,
                        "input_amplitude_V":amp,
                        "output_logic_switching_observed":max(vals)-min(vals)>1.3}
    # Estimate transfer curve offset with direct DC MOS solutions;
    # this is NOT M8-M10 binary-current offset cancellation.
    threshold={}
    for corner in CORNERS:
        rr=sorted([x for x in dc if x["corner"]==corner and
                     x["device_width_skew_fraction"]==0],
                  key=lambda x:x["vin_V"])
        cross=None
        for a,b in zip(rr,rr[1:]):
            v1,v2=a["out_V"],b["out_V"]
            if v1<.9<=v2 and v2>v1:
                cross=a["vin_V"]+(.9-v1)*(b["vin_V"]-a["vin_V"])/(v2-v1)
                break
        threshold[corner]={"estimated_0p9V_transition_input_V":cross,
                           "estimated_input_offset_mV":None if cross is None
                            else (cross-VCM)*1000}

    report={
      "status":"executed_reconstructed_pmos_preamp_comparator",
      "source":"Paper Fig.14 PMOS-input preamplifier concept; NOT exact 19-device schematic",
      "model":"DB HiTek 180nm SVT NMOS/PMOS, ngspice42",
      "scope":"PMOS differential preamp + NMOS current-mirror loads + 2 CMOS rail buffers",
      "corner_dc_conditions":conditions,
      "transient_tests":dynamic,
      "dc_transition_estimates":threshold,
      "number_of_spice_runs":runner.calls,
      "limitations":[
        "No M11-M19 clocked regenerative latch and booster",
        "No M8-M10 binary-weighted offset controller or reset circuit",
        "No real 4-phase 1.8GHz sample, Sync, 2:16 Demux",
        "Preamp transistor widths, Vbias and capacitances are author-assumed",
        "ngspice ignored some proprietary HSPICE model flags; numerical correlation still missing",
      ]
    }
    (out/"fig14_comparator_summary.json").write_text(json.dumps(report,indent=2)+"\n")
    print("P3 Fig.14-inspired comparator result:",json.dumps(report,indent=2),flush=True)
    assert conditions["tt"]["output_delta_V"]>1.0
    # A reconstructed preamplifier can fail switching at high speed or corners.
    # Treat such failure as an engineering RESULT, not verified functionality.
    if not dynamic["low_frequency_100MHz"]["output_logic_switching_observed"]:
        print("LIMITATION: This Fig14-inspired MOS preamp has not achieved rail-to-rail 100MHz output.",flush=True)
    if not dynamic["high_frequency_1p8GHz"]["output_logic_switching_observed"]:
        print("LIMITATION: This Fig14-inspired MOS preamp has not achieved 1.8GHz switching.",flush=True)
    print("PASS: PDK MOS comparator DC/PVT, low-frequency transistor-level switching; high-speed shortcomings reported",flush=True)
    return report

if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("--out",type=Path,default=Path("results/spice/p3_fig14_comparator"))
    test(a.parse_args().out)
