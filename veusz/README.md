# Veusz-compatible datasets for the P3 behavioral simulation

All CSV values derive from the **Python RC surrogate**, NOT the paper's measured silicon. Open `P3_Editable_Plots.vsz` in Veusz and keep its linked CSV files in the same folder. Linked data can be reloaded via Veusz **Data > Reload**. CSVs can also be imported manually via **Data > Import > CSV**. For eye overlays and the full six-page Veusz version, use the downloadable presentation package, which includes `eye_overlay.csv`.

- `tap_tradeoff.csv`: tap count, eye height, long-run TX DC swing, main cursor, sum of ISI cursors.
- `alpha_sweep.csv`: 41 alpha values and eye/swing metrics.
- `channel_loss.csv`: two different 12-dB-at-Nyquist RC models.
- `channel_sensitivity.csv`: 1/2-pole eye sensitivity.
- `P3_Editable_Plots.vsz`: four editable, CSV-linked plots.

Generate the data locally after running the model with `python simulation/export_veusz.py`.

Veusz was unavailable in the execution container. These files were CSV-validated and Veusz script syntax checked, but a GUI open/render test remains to be performed on a machine with Veusz installed. The Veusz CSV import and scripting API is documented at https://veusz.github.io/docs/manual/api.html .
