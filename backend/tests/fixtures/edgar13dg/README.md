# Real SEC Schedule 13D/13G filings used as test fixtures

`*.xml` files are structured Schedule 13D/13G documents; `*.html` files are EDGAR's own header
pages for older free-form filings ("SC 13D", "SC 13G"). All are stored byte-for-byte as EDGAR
served them. `manifest.json` holds each filing's index metadata.

| Accession | Issuer | What it covers |
|---|---|---|
| 0000921895-26-000120, -002474, -002783 | GameStop | Ryan Cohen's 13D amendments 14, 15 and 21: same shares at a lower percentage, then more shares |
| 0000921895-24-001394 | GameStop | Free-form SC 13D/A filed by RC Ventures LLC |
| 0000102909-26-001393 | GameStop | Vanguard 13G/A reporting zero: an exit below 5% |
| 0000093751-25-000469, -000620, 0000093751-26-000274 | Nike | State Street 13G filings in three successive quarters |
| 0002100119-26-000802, 0002100121-26-001085, 0001422849-26-000147 | Nike | Other passive holders (two Vanguard entities, Capital World) |
| 0000102909-26-001994 | Nike | The Vanguard Group 13G/A reporting zero |
| 0001104659-24-021564, 0001086364-24-004600 | Nike | Free-form SC 13G/A filings (Vanguard, BlackRock) |
| 0001104659-24-021208 | Intel | Free-form SC 13G/A about Intel |
| 0000050863-24-000116 | MariaDB | Filed *by* Intel about its MariaDB stake; listed in Intel's index and must be skipped |
