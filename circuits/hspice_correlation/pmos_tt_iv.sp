* DB HiTek 180 nm 1.8-V SVT PMOS reference I-V for LICENSED HSPICE
* NOT run in GitHub Actions: proprietary HSPICE executable unavailable.
* D,G,S,B,SUB: well/bulk=1.8V, p-substrate=0V.
.lib './pdk_private/1830BD18BA_Rev3p6p0.l' tt_svt018
.option post=0
.temp 27
VSUP s 0 1.8
VDS d 0 1.3
VGS g 0 1.8
XMP d g s s 0 pch_svt_1p8v width=1u length=0.18u multi=1
.dc VGS 1.8 0 -0.1
.print dc v(g) i(VDS)
.end
