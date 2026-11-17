# Real SEC filings used as test fixtures

Every `*.xml` file here is an ownership document (Form 3, 4, 5 or an amendment) downloaded from
SEC EDGAR and stored byte-for-byte, unmodified. Filings are public records. `manifest.json`
holds each filing's metadata exactly as EDGAR's submissions index reported it (form, filing
date, acceptance timestamp, primary document path).

Original of any file: `https://www.sec.gov/Archives/edgar/data/<cik>/<accession without dashes>/`
(the live test `test_edgar_live.py` re-downloads one and checks it is byte-identical).

| Accession | Issuer | What it covers |
|---|---|---|
| 0000050863-26-000195 | Intel | CEO open-market purchase, with other holdings listed |
| 0000050863-26-000194 | Intel | RSU vesting: exercise (M), tax withholding (F), derivative table |
| 0001127602-23-006774 | Intel | Sale under standing trading instructions; pre-2023 form (no 10b5-1 checkbox) |
| 0001127602-24-021794 | Intel | CEO purchases through one trust while holding shares in eight lots |
| 0001127602-25-002794 | Intel | Form 5, inheritance (W) |
| 0000050863-25-000199 | Intel | Form 3, holdings only |
| 0001127602-23-002926 | Intel | Gifts (G) |
| 0001127602-25-010360 | Intel | Shares acquired from the company at a price (code A): paid for, but not open market |
| 0000050863-25-000099 | Mobileye | Filed by Intel as an owner of Mobileye; appears in Intel's index and must be skipped |
| 0000320193-23-000096 | Apple | 10b5-1 plan sales stated in footnotes while the checkbox is unchecked |
| 0000320193-24-000049 | Apple | Vesting, withholding, plan sales, and one sale the plan footnotes do not cover |
| 0001140361-26-023363 | Apple | Discretionary open-market sale by a director |
| 0000320187-26-000049 | Nike | Director purchase whose footnote is policy boilerplate mentioning 10b5-1 |
| 0001127602-24-019550 | Nike | Purchase made under a 10b5-1 plan |
| 0000320187-26-000051 / -000053 | Nike | CEO purchase and the Form 4/A correcting its price |
| 0000320187-26-000055 / -000129 | Nike | Gift and the Form 4/A restating it |
| 0001127602-24-014652 | Nike | Option exercise and same-day sale of the exercised shares |
| 0000320187-26-000013 | Nike | Plan sale indicated only by the 10b5-1 checkbox |
| 0000320187-26-000045, -000043 | Nike | Two more directors buying in the same fortnight (cluster) |
| 0001437749-24-028607 | Texas Pacific Land | Joint filing by a director and a 10% owner |
| 0001207097-23-000061, 0001056823-23-000012 | Texas Pacific Land | The same director and fund filing jointly, then the fund alone, a day apart |
| 0001088011-26-000004 | Carvana | Trades made by an investment manager without the director's knowledge |
