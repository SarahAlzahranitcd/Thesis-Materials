# Study 5: Metadata-Guided LLM Mapping Generation

This folder contains the materials and data for Study 5, a controlled experiment evaluating whether lifecycle-based metadata can improve the semantic correctness and completeness of LLM-generated declarative mappings. Study 5 corresponds to Chapter 5, Section 5.7 of the thesis.

## Purpose

Study 5 tested whether lifecycle-based metadata, structured according to LMMD phases, can serve as a reusable template for guiding LLM mapping generation. Six real-world scenarios were evaluated across the three declarative mapping types: RML uplift mapping (S1A, S1B), ontology alignment (S2A, S2B), and interlinking (S3A, S3B). For each scenario, the same LLM was executed twice with the same task description: once without metadata (baseline) and once with the selected lifecycle-based metadata included as structured contextual input (metadata-guided).

## Contents

* `prompts/` - The baseline and metadata-guided prompts used for each of the six scenarios, as well as generated results organised by mapping type.
