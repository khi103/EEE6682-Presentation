* DB HiTek 180 nm 1.8-V SVT NMOS reference I-V for LICENSED HSPICE
* NOT run in GitHub Actions: proprietary HSPICE executable unavailable.
* Execute from the repository root where pdk_private holds authorized model.
.lib './pdk_private/1830BD18BA_Rev3p6p0.l' tt_svt018
.option post=0
.temp 27
VDS d 0 0.5
VGS g 0 0.0
XMN d g 0 0 nch_svt_1p8v width=1u length=0.18u multi=1
.dc VGS 0 1.8 0.1
.print dc v(g) i(VDS)
.end
