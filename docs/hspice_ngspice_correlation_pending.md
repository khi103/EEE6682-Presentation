# HSPICE–ngspice correlation procedure (reference pending)

The DB HiTek PDK was authored for HSPICE; ngspice-42 silently ignores
HSPICE model parameters such as lref, wref, hspver, binflag, vfbflag, tlev,
tlevc. Therefore successful ngspice DC and Transient runs **do not** prove
numerical equivalence to licensed HSPICE.

The following small DUTs have now been written for a *later licensed HSPICE*
comparison at 27°C, TT, W/L=1µm/0.18µm, VDS/VSD=0.5V:

- `circuits/hspice_correlation/nmos_tt_iv.sp`
- `circuits/hspice_correlation/pmos_tt_iv.sp`

The ngspice companion benchmark is **actually executed** automatically by
`simulation/p3_device_iv_ngspice.py`: NMOS/PMOS, TT/FF/SS/FS/SF,
VDS/VSD=0.5/1.0V and 0–1.8V gate bias. Output data:
`results/spice/p3_device_iv/dbhitek_ngspice_device_iv.csv`.

Run the HSPICE DUT in a *licensed* HSPICE environment containing the
original PDK, not a stripped/ngspice-converted model. Export its printed I–V
curves as CSV with columns:

```
corner,device,Vds_or_Vsd_V,Vgs_or_Vsg_V,absolute_drain_current_A
tt,nmos,0.5,0.0,0.0
...
```

Compare the exported CSV to ngspice using
`python scripts/compare_hspice_ngspice_iv.py --hspice PATH.csv`.

A numeric relative-current deviation is reported for gate voltages where
the reference current exceeds 1µA. Do not claim any HSPICE correlation
until a real HSPICE reference file is supplied and parsed.

**Status**: HSPICE reference not available in connected GitHub CI and no
valid HSPICE executable/license present. ngspice I–V sanity data is a
separate, limited verification.
