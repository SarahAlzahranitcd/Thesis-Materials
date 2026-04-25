# Study 4: Mapping Reuse Experiment Based on Metadata

This folder contains the materials and data for Study 4, a scenario-based expert study investigating whether lifecycle-based metadata supports reuse decision-making for declarative mapping artefacts. Study 4 corresponds to Chapter 5, Section 5.6 of the thesis.

## Purpose

Study 4 compared two metadata representations of the same mapping artefacts to evaluate whether lifecycle-based metadata improves reuse decisions beyond what current FAIR-oriented practice already provides. Representation A is a FAIR-IMPACT-style artefact-level metadata description. Representation B is the MMV lifecycle-based metadata model. Ten participants reviewed three real-world mapping artefacts (a Silk interlinking rule, a YARRRML/RML uplift mapping, and an OAEI 2024 Anatomy ontology alignment) and decided whether each artefact could be reused as a starting point in a new project based on the metadata alone.

## Contents

* `questionnaire/` - The study instrument as deployed via the MetaSEMAP web application: study information and consent page, the three scenario pages with embedded artefact excerpts and the two metadata representations, and the final questions page.
* `raw-data/` - Anonymised participant responses (10 CSV files, one per participant).
* `results/` - Processed tables corresponding to thesis Tables 5.21–5.24.
