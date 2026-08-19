# vatic examples

Worked examples you can run, read, and check your own results against.

## Double-D seal gland tolerance stack-up

A PSA-backed double-D single-hole gland is specified by eight dimensions, each
with a symmetric tolerance. Following the convention used throughout the
original model, a `±t` tolerance is read as a **three sigma** bound, so each
dimension is modelled as `Normal(nominal, t / 3)`.

Two characteristics are checked against their requirements:

| Characteristic | Formula | Lower | Upper |
| --- | --- | --- | --- |
| Gland Fill % | `seal area / groove area` | 0.75 | 1.00 |
| Seal Comp. % | `1 - groove height / seal height` | 0.25 | 0.50 |

### Run it

```sh
python examples/seal_tolerance.py
```

This runs 10,000 Latin-hypercube trials through `vatic`'s own API — no
spreadsheet involved — and prints the mean, standard deviation, variance,
skewness, kurtosis, percentiles and the full process-capability family for
every characteristic.

### What the answer should look like

At nominal dimensions the model is deterministic, so the simulated means have
a closed form to check against:

| Characteristic | Nominal |
| --- | --- |
| Core hole area | 0.002969 in² |
| Seal area | 0.015400 in² |
| Groove area | 0.015210 in² |
| Gland Fill % | 1.0125 |
| Seal Comp. % | 0.27778 |

Note that **Gland Fill % overfills at nominal** — its mean sits above the 1.00
upper limit, so a negative `Cpk` and a defect rate in the hundreds of thousands
of PPM is the correct result, not a bug. Seal Comp. % comfortably passes. That
contrast is the point of the example: one characteristic that fails and one
that does not.

`tests/test_seal_example.py` asserts all of this.

## Rebuilding the workbook

`seal_tolerance.xlsx` holds the same model as a spreadsheet, with the input
dimensions in `C8:C15`, the requirements in `C19:D20`, and the characteristics
in `C24:C26` and `C30:C31`. Formulas are written against workbook names
(`sh`, `sw`, `d`, `cc`, `gh`, `gw`, `flat1`, `flat2`, `ca`, `sa`, `ga`), which
keeps them readable and is what a spreadsheet-driven run will bind to.

Regenerate it from source with:

```sh
uv pip install openpyxl
python examples/build_seal_workbook.py
```

## Provenance

The model, its dimensions and its formulas come from the worked example that
ships with the original **vatic** project by Abraham Lee
(<https://github.com/tisimst/vatic>), which drove the same calculation through
Microsoft Excel over COM.

That repository carries no licence, so its workbook file is not redistributed
here. `build_seal_workbook.py` rebuilds an equivalent workbook from the same
published dimensions and formulas instead, which also means the spreadsheet is
reproducible from source control rather than being an opaque binary.

## Differences from the original

The statistics deliberately follow the original conventions so results line up:
population variance, skewness as the standardised third moment with no
sample-size correction, and Pearson kurtosis where a normal distribution sits
at 3.0.

The capability metrics do **not** reproduce the original's arithmetic, which
had defects:

- it used the normal **density** where the **cumulative** distribution is
  required, so every `p(N/C)`, `PPM`, `Zst` and `Zlt` value was wrong;
- it wrote the `Cpm`/`Ppm` exponent with `^`, which is bitwise XOR in Python,
  so those two metrics could never be computed at all;
- it accepted a `zshift` argument and then ignored it, leaving `Zst` and `Zlt`
  identical.

All three are fixed here, and `tests/test_analytics.py` pins each fix down
against an independent derivation.
