---
id: population-estimates
title: "Population estimates: definitions and sources"
publisher: "TerraPulse methodology note (summarises World Bank WDI metadata)"
published: "2026-10-21"
source_url: "https://data.worldbank.org/indicator/SP.POP.TOTL"
approved: true
---
# Total population (SP.POP.TOTL)

Total population is based on the de facto definition of population, which counts all residents regardless of legal status or citizenship. The values published in the World Development Indicators (WDI) are midyear estimates, so TerraPulse assigns each annual value a reference date of 1 July of that year.

WDI population figures are compiled from the United Nations World Population Prospects, national statistical offices, Eurostat and other sources. Between censuses the values are modelled estimates, not live enumerations. A census itself is an observed count at a specific date, but WDI publishes harmonised estimates rather than raw census counts.

# Population growth rate (SP.POP.GROW)

The annual population growth rate for year t is the exponential rate of growth of midyear population from year t-1 to t, expressed as a percentage. Because it is an exponential rate, a growth rate of r percent implies population(t) = population(t-1) x exp(r/100).

# How TerraPulse uses these figures

TerraPulse imports a dated, checksummed snapshot of the WDI API and treats every value as an estimate published by the source. TerraPulse does not adjust, smooth or nowcast the values. Derived numbers (absolute change, percentage change, compound annual growth, shares and rankings) are calculated deterministically in Python from the imported values. The AI assistant explains these numbers but never calculates or overrides them.
