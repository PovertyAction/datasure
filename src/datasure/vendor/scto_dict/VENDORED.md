# Vendored surveycto_python_dict

These modules are copied from
[PovertyAction/surveycto-python-dict](https://github.com/PovertyAction/surveycto-python-dict)
(MIT, see `LICENSE`). They give DataSure the form contract from the compiled XForm
(`xml_contract`, with the expression evaluator `xpath`), its flat question list
(`questions`) and the typed cast of wide-JSON submissions (`cast`). Upstream's dictionary, stats, codebook and PII
modules join `MODULES` in `scripts/vendor_scto.py` when DataSure uses them.

Source commit: `d6f54f9ae5792e23c5303d36e0fae5b1550d3401`

Do not edit these files. Change them upstream, then re-vendor:

```sh
just vendor-scto <path to surveycto_python_dict checkout> <git ref>
```

`scripts/vendor_scto.py` rewrites `surveycto_python_dict.` imports to
`datasure.vendor.scto_dict.` and applies its `PATCHES`. Each patch is pending
upstream; drop it from the script once upstream has it.

| Module | Patch |
| --- | --- |
| `xml_contract` | `parse_contract` also accepts XML bytes |

Not vendored: `cli`, `flow`, `database`, `mcp_server` and `api`. DataSure has its
own SurveyCTO client and storage.
