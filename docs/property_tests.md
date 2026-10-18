# Property-based tests

`tests/test_properties.py` uses [Hypothesis](https://hypothesis.readthedocs.io/). An example-based test checks a
case someone thought of; a property states a rule that must hold for every input, and Hypothesis searches for a
counterexample and shrinks it to the smallest failing input.

## What is covered
| Area | Properties |
|---|---|
| `parse_price` | Any of 8 formats (₹, Rs., INR, MRP:, spaces) with plain, western or Indian digit grouping parses to the exact two-decimal value; a range is never guessed; text without digits is never a price (never `0.00`); a parsed price re-parses to itself |
| `parse_count` | `1,234` and `(1,234)` are exact; `K` and `M` suffixes scale exactly; missing values are null, never 0 |
| `parse_rating` | Valid ratings round trip in 4 text styles; an out-of-range rating is null |
| all three parsers | Never raise on arbitrary text; only return well-formed values |
| `product_key` | The key ignores the title slug and any tracking parameters |
| deduplication | One unit per placement and the first occurrence wins; idempotent; the title alone never decides a duplicate; the same product as SP and Organic stays two placements |
| `validate_entries` | Every entry is accepted or rejected exactly once (nothing vanishes); agrees with the older `validate_units`; `duplicate_placement` versus `cross_page_duplicate` matches whether the pages differ |
| brand normalization (`tests/test_brand.py`) | Normalizing twice changes nothing and never returns an empty brand; the grouping key ignores case and padding |
| `assign_ranks` | Absolute and per-type ranks are continuous, and splitting results into pages never changes them |

## Bugs the properties found
I fixed both in `src/parsers/product_parser.py`.
1. **`parse_rating` read the fractional digit of an out-of-range rating on its own.** `"6.0"` returned `0.0` and
   `"7.5"` returned `5.0`, instead of null. The ordinary tests only had examples such as `"7"`.
2. **`product_key` took the first `/p/` segment.** A title slug that is exactly `p` (`/p/p/100000_aa`) returned `p`.
   The pattern now requires the product segment to be the last one in the path.

## Running
```
python -m pytest tests/test_properties.py            # default profile: 200 examples each, fixed seed
```
The default profile is deterministic, so a CI failure reproduces locally, and it stores no example database. Hypothesis still creates a small `.hypothesis/` cache folder; it contains its own `.gitignore`, so Git ignores it and nothing needs adding to the project's `.gitignore`.
To search harder (3,000 examples, random seeds):
```
$env:HYPOTHESIS_PROFILE="explore"; python -m pytest tests/test_properties.py      # PowerShell
set HYPOTHESIS_PROFILE=explore && python -m pytest tests/test_properties.py       # cmd
```
If it ever fails, copy the printed `Falsifying example` into a normal test before fixing, so it stays covered.

## Limits
- Properties describe the parsing helpers and the placement logic, not the full HTML parser.
- Lenient inputs are not rejected: `parse_price("1e5")` returns `1.00` (the exponent is ignored) and `"12,34"` is read as `1234.00`. Real prices use neither.
- A run covers only the generated examples; a passing run is evidence, not proof.
