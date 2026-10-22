# US natality ETL reusability, 2018–2024


Scope: the main U.S. natality public-use files, with each year loaded into its own destination. This assessment concerns the local template and mapping inspected on the assessment date, not a verified deployed pipeline.

The current ETL can parse the retained fields for every year from 2018 through 2024, but the current mapping is not fully correct across all those years. The main confirmed conflict is plurality (`DPLURAL`).

Reviewed inputs:

- ETL_US_BirthData_to_OMOP.json
- Merged_US_Birth_Data_updated_261020.csv
- Annual guides: 2018-2024.

## Field differences relative to 2022

All **109 fields retained by the current ETL have the same start/end positions** in all seven guides. Stable positions do not guarantee identical meanings.

| Field / position | 2022 benchmark | Differences in other years | Effect on current ETL |
|---|---|---|---|
| **`DPLURAL`, 454** | `1` single; `2` twin; `3` triplet; **`4` quadruplet or higher** | **2018–2019:** `4` means quadruplet; **`5` means quintuplet or higher**. 2020–2024 use the 2022 categories. | **Confirmed mapping gap:** code `5` has no mapping. Code `4` is currently mapped as “Quadruplet birth,” which needs review for the broader 2020–2024 category. |
| **`ATTEND`, 433** | Code `3`: Certified Nurse Midwife / Certified Midwife (`CNM/CM`) | 2018–2019 describe code `3` as Certified Nurse Midwife (`CNM`). 2020 says Certified Nurse Midwife `(CNM/CM)`; 2021 matches 2022. | Parsing works. Review whether the shared OMOP mapping deliberately groups these categories. |
| **`DOB_YY`, 9–12** | `2022` | Contains the corresponding source year, 2018–2024. | Current code uses the source year correctly. No year-specific parser required. |
| **`MRACEHISP`, 117** | Race/Hispanic categories | 2018–2019 include additional explanatory references to bridged race. The listed categories remain the same. | No confirmed mapping change required for this field. |
| **Filler fields** | Generic `FILLER` names; positions 1–8 have length 8. | Earlier guides use names such as `FILLER_M` and `FILLER_X`, and incorrectly list length 6 for positions 1–8. | No effect: the parser uses explicit positions and excludes filler. |

The plurality difference is documented on page 32 of the 2018 and 2019 guides, compared with page 31 of the 2022 guide.

## Applicability by source year

| Source year | Current parser | What prevents an unconditional “fully compatible” verdict? |
|---|---|---|
| **2018** | Compatible for all retained fields | Missing `DPLURAL=5` mapping; review historical `ATTEND=3` semantics. |
| **2019** | Compatible for all retained fields | Same as 2018. |
| **2020** | Compatible for all retained fields | `DPLURAL=4` as “quadruplet or higher”; clarify `ATTEND=3` wording. |
| **2021** | Compatible for all retained fields | `DPLURAL=4` as “quadruplet or higher”. |
| **2022** | Benchmark | `DPLURAL=4` as “quadruplet or higher” |
| **2023** | Compatible for all retained fields | `DPLURAL=4` as “quadruplet or higher”; the `MRACE6` documentation correction requires no parser change. |
| **2024** | Compatible for all retained fields | Same as 2023. |

## Required fixes and remaining verification

1. **Make plurality mappings year-aware.** For 2018–2019, cover exact quadruplets (`4`) and quintuplets-or-higher (`5`). For 2020–2024, preserve the broader meaning of `4`, sugggest to apply explicit normalization rule based on source `DOB_YY`.
2. **Confirm the intended `ATTEND=3` harmonization.** The parser needs no change. Document whether historical CNM and later CNM/CM are intentionally grouped.
3. **Add input and unmapped-value checks.** The current bronze node does not explicitly enforce the expected record length or a consistent source year.

One shared parser remains practical. The variable `nat2022_filename` can accept another year’s filename, birth year comes from the source `DOB_YY`.
