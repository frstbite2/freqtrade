# Real SEC Form 13F submissions used as test fixtures

Every `*.txt` file is a complete 13F submission downloaded from SEC EDGAR and stored
byte-for-byte, unmodified. `manifest.json` holds each filing's metadata as EDGAR's index
reported it. Originals: `https://www.sec.gov/Archives/edgar/data/<cik>/<accession without dashes>/`.

| Accession | Manager | What it covers |
|---|---|---|
| 0001172661-22-002568 | Pershing Square | Filed in 2022: values in thousands of dollars |
| 0001172661-24-005218, 0001172661-25-001119 | Pershing Square | Consecutive quarters (Sep and Dec 2024) |
| 0001172661-25-001497 | Pershing Square | "New holdings" amendment: a position that was confidential in the Dec 2024 report |
| 0001172661-25-002315, 0001172661-26-002336 | Pershing Square | Later quarters |
| 0001172661-26-003777 | Pershing Square | 13F-NT notice: holdings reported by another manager |
| 0001013594-25-000294, 0001013594-25-000512 | Elliott | A report and its full restatement |
| 0000919574-24-003172, 0000919574-24-004713 | Tiger Global | Mar and Jun 2024, across Nvidia's 10-for-1 split |
| 0001656456-24-000002, 0001656456-24-000003 | Appaloosa | The same two quarters |
| 0001536411-26-000006 | Duquesne | Filed in 2026 with values still in thousands |
