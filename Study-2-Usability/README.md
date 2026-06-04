# Study 2: Usability Evaluation of MetaSEMAP

This folder contains the materials and data for Study 2, a usability evaluation of MetaSEMAP, a web-based tool for annotating declarative mappings with lifecycle metadata. Study 2 corresponds to Chapter 5, Section 5.4 of the thesis.

## Purpose

Study 2 evaluated the usability of MetaSEMAP and the interpretability of its metadata representations across three types of declarative mappings (uplift mapping, ontology alignment, and interlinking) with 46 participants from a knowledge and data engineering MSc course. The study captured perceived usability through a 14-item PSSUQ-based survey, completion-time measurements, participant preference for Named Graph versus RDF-star representation, and qualitative feedback on tool design.

## Contents

- `questionnaire/` - The survey instrument and the three scenario briefs distributed to participants.
- `raw-data/` - Anonymised survey responses (`MetaSEMAP_Survey.csv`) and the annotation files produced by participants in both Named Graph and RDF-star formats. Note: The raw annotation files in the Named-graph and RDF-star folders were produced by the initial version of MetaSEMAP used during the study. In that version, optional fields left blank by the user were serialised as empty string literals (e.g. metag:mappingAssumptions "" ;). This behaviour was corrected in MetaSEMAP v2, in which unpopulated optional fields are omitted entirely and no triple is created for blank values. The empty string literals in these files reflect the tool state at the time of data collection and do not affect the validity of the usability evaluation findings.
- `results/` - Processed data

