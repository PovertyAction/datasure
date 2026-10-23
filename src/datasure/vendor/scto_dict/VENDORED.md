# Vendored surveycto_python_dict

These modules are copied from
[PovertyAction/surveycto-python-dict](https://github.com/PovertyAction/surveycto-python-dict)
(MIT, see `LICENSE`). They give DataSure the form contract from the compiled XForm
(`xml_contract`, with the expression evaluator `xpath`), its flat question list
(`questions`), the typed cast of wide-JSON submissions (`cast`), and the variable
dictionary, skip-logic stats, codebook writer and rule-based PII flags
(`dictionary`, `stats`, `codebook`, `pii`, with `contract` and `survey`).

Source commit: `3f5de311dd483791e6cb7b38b8d393291866ed1b`

Do not edit these files. Change them upstream, then re-vendor:

```sh
just vendor-scto <path to surveycto_python_dict checkout> <git ref>
```

`scripts/vendor_scto.py` rewrites `surveycto_python_dict.` imports to
`datasure.vendor.scto_dict.` and applies its `PATCHES`, changes pending
upstream. There are none: the source commit is on upstream's
`feat/in-memory-library` branch (`parse_contract` reads bytes, `stats_rows`,
`save_codebook`, `classify` without an analyzer). Re-vendor from upstream
`main` once it merges.

Not vendored: `cli`, `flow`, `database`, `mcp_server` and `api`. DataSure has its
own SurveyCTO client and storage.
