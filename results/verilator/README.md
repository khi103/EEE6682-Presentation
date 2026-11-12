# Executed Verilator FFE tap-count results

Both CSV files were derived from the executed professor lecture SystemVerilog engine (Verilator), not from a Python-only duplicate.

- `verilator_original_56G_taps.csv`: EXACT original instructor `sim3_ffe.py` run at 56 Gb/s. Source: https://github.com/khi103/serdes-lecture-site/actions/runs/43142270060
- `verilator_P3_3p6G_taps.csv`: patched working copy of `linksim.py` plus original `link.sv`, 3.6 Gb/s, synthetic 2-pole RC -12dB @1.8 GHz, alpha=0.30 2-tap and 3/5-tap ZF. Source: https://github.com/khi103/serdes-lecture-site/actions/runs/43139646362
- Veusz project: `../../veusz/P3_Verilator_Actual_Cross_Model.vsz`, linked to the two CSVs.

These datasets MUST NOT be interpreted as comparable silicon performance. 56-Gb/s lecture channel, 3.6-Gb/s synthetic RC channel, and measured paper PCB/RG58 channel are different.
