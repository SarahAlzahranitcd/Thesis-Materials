# MMV — Mapping Metadata Vocabulary

This folder contains the two releases of the MMV ontology developed during this thesis.

## Versions

- **`MMV-V0.1/`** - Initial release. Used in Studies 3 and 4 of the thesis.
- **`MMV-V0.2/`** - Current release. Used in the refined MetaSEMAP tool.

## Live documentation

- v0.2: https://sarahalzahranitcd.github.io/MMV-V02/
- v0.1: https://sarahalzahranitcd.github.io/MMV-Ontology2/

## What changed in v0.2
Added classes:
- `mmv:ValidationReport` - for SHACL or other constraint-checking outputs

Added properties:
- `mmv:hasValidationReport` - links a TestingActivity to its ValidationReport
- `foaf:homepage` - stakeholder homepage (reused from FOAF)
- `foaf:organization` - stakeholder organisation (reused from FOAF)
- `prov:wasRevisionOf` - links a mapping artefact to its previous version (reused from PROV-O)

- Competency questions and FAIR Alignment tables.
