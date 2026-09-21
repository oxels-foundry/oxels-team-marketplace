# OOXML schemas used by the schema invariant

Unmodified XSD files from ECMA-376, 5th edition, downloaded from
ecma-international.org on 2026-09-09:

- `transitional/`: Part 4, Transitional Migration Features
  (`OfficeOpenXML-XMLSchema-Transitional.zip` inside
  `ECMA-376-4_5th_edition_december_2016.zip`).
- `opc/`: Part 2, Open Packaging Conventions
  (`OpenPackagingConventions-XMLSchema.zip` inside
  `ECMA-376-2_5th_edition_december_2021.zip`).

Every file here is byte-for-byte as published. Nothing in them is edited.

## Why this is a subset of the upstream zips

The invariant loads three entry points — `wml-driver.xsd`,
`opc/opc-contentTypes.xsd`, and `opc/opc-relationships.xsd` — and only the
files reachable from them by `schemaLocation` are kept. The upstream zips also
carry the SpreadsheetML (`sml.xsd`) and PresentationML (`pml.xsd`) grammars,
the VML files, and the document-property and bibliography schemas; a
WordprocessingML consumer never resolves them, so they are not vendored.

The VML schemas look load-bearing and are not: `wml.xsd` admits VML only
through `xsd:any processContents="lax"`, which validates against a schema for
that namespace when one is loaded and skips the content when none is. No entry
point here has ever loaded `vml-main.xsd`.

To re-add a file, take it from the upstream zip named above without editing it.

Word's own extension namespaces (w14, w15, w16*) have no schema here. The
invariant strips elements and attributes outside the ECMA namespaces before
validating, which is what the `mc:Ignorable` mechanism in ECMA-376 Part 3
tells a consumer to do.
