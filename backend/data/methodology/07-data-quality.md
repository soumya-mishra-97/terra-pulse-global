---
id: data-quality
title: "Data quality, comparability and TerraPulse safeguards"
publisher: "TerraPulse methodology note"
published: "2026-10-21"
source_url: "https://datahelpdesk.worldbank.org/knowledgebase/articles/906531"
approved: true
---
# Revisions and comparability

Each WDI release can revise past values when new census or survey data arrive. TerraPulse stores the release version, retrieval time and checksum of every imported snapshot and never mixes values from different releases in one comparison. Comparisons between countries use the same metric, the same source and the same reference years.

# Aggregates

Regional, income-group and world figures in WDI are aggregates computed by the World Bank. Regional definitions follow World Bank groupings, which differ from UN regional groupings, so regional figures from different organisations are not directly comparable.

# Missing values

Some indicators lag the population series by one or more years, and some economies lack recent values. TerraPulse reports the latest available year for each indicator separately and marks missing indicators as "Data unavailable" instead of filling gaps.

# Freshness

TerraPulse marks data as stale when the latest reference date is older than a configurable threshold (730 days by default). Stale data remains usable but is flagged in the interface, the API and generated reports.
