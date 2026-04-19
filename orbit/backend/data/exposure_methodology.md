# Exposure Weights Methodology

## What These Scores Represent

The values in `exposure.json` are **supply chain sensitivity scores**, not revenue percentages. They estimate how much a given geopolitical disruption in a country would impact the company's operations or output.

## Why Scores Can Sum >100%

Supply chains have overlapping dependencies. For example, a Taiwan disruption affects both chip fabrication and downstream assembly, so AAPL's country scores sum well above 100%.

## Key Calibration Notes

- **AAPL US (43%)**: Derived from Apple 10-K FY2025 Americas segment revenue share, used as a proxy for US revenue exposure.
- **AAPL TW (85%)**: TSMC fabricates 100% of Apple's custom silicon. Apple is nearly fully dependent on Taiwan for chip supply despite earning 0% of revenue there. Source: TSMC Annual Report (Taiwan fab capacity >90%).
- **NVDA CN (15%)**: Reflects post-export-control reality; was ~25% pre-restrictions. Source: NVIDIA 10-K, data center segment geographic breakdown.
- **TSM TW (95%)**: TSMC's own concentration in Taiwan. Source: TSMC Annual Report.

## Sources

- Apple 10-K FY2025
- TSMC Annual Report FY2025
- NVIDIA 10-K FY2025

## Maintenance

Scores are manually calibrated and should be updated quarterly with earnings data.
