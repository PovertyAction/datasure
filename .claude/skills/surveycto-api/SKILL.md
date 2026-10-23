---
name: surveycto-api
description: Use this skill when working with the SurveyCTO API in DataSure — downloading submissions, the compiled form XML, server datasets or attachments, encrypted forms, the typed import, or SurveyCTO credentials. Covers utils/scto_api.py, connectors/scto.py and the datasure.surveycto contract and cast.
---

# SurveyCTO API in DataSure

## Layers

```text
utils/secure_credentials.py   password in the OS keyring, never on disk
  └─ utils/scto_api.py         SurveyCTOAPIClient: HTTP only, raises SurveyCTOAPIError
       └─ connectors/scto.py   SurveyCTOClient.import_data(): routing, typing, storage
            ├─ surveycto/          parse_contract (XML -> FormContract), cast_wide
            └─ utils/duckdb_utils.py   raw.duckdb; form_definitions in logs.duckdb
```

`SurveyCTOAPIClient` uses a `requests` session with Basic auth. The base URL is
`https://{server}.surveycto.com/api/v2`; the console and form endpoints sit at the
server root.

## Endpoints

| Method | Endpoint | Returns |
| --- | --- | --- |
| `download_form_data_json(form_id, params, private_key)` | `GET /api/v2/forms/data/wide/json/{id}`; `POST` with the key as multipart `private_key` | Wide JSON rows; every value is a string |
| `download_form_xml(form_id)` | `GET /forms/{id}/xml` | Compiled XForm bytes |
| `list_datasets()` | `GET /api/v2/datasets`, following `nextCursor` | Dataset metadata (`id`, `title`, ...) |
| `download_dataset_csv(dataset_id)` | `GET /api/v2/datasets/data/csv/{id}` | CSV bytes |
| `list_forms()` | Console `forms-groups-datasets/get`, CSRF login | Forms with `encrypted` |
| `download_form_definition(form_id)` | Console `/forms/{id}/design/`, CSRF login | XLSForm design JSON |
| `download_attachment_from_url(url, private_key)` | Attachment URL | Bytes |

The design JSON serves the replication package's XLSForm and the media field list
for attachments. Typing uses the XML.

## Import (`SurveyCTOClient.import_data`)

1. Every ID imports as a form first. If its XML download raises
   `FormNotFoundError` (404) and the ID is on `list_datasets()`, it imports as a
   server dataset CSV with no typing. Every other error propagates: there is no
   fallback.
2. A form import downloads the XML, parses it with `parse_contract`, casts the rows
   with `cast_wide` and converts with `typed_frame`. That gives form types (int ->
   Int64, decimal -> Float64, date -> Date, select_multiple binaries -> Int8,
   numeric select_one -> Int64), naive UTC timestamps and an Int64
   `formdef_version`.
3. It saves the frame to `raw.duckdb`, then stores the XML with
   `save_form_definition` (one row per alias and form version). `load_form_definition(alias)`
   returns the latest version's XML, or `None`.

## Requests

- **Date filter.** `date` is the oldest `CompletionDate` in epoch seconds.
  `date=0` is throttled to one full pull per quiet period (HTTP 417), so the floor
  is `SurveyCTOConfig.default_date` (2010-01-01 UTC). Every refresh is a full pull
  until #340 is fixed.
- **Encrypted forms.** The import log stores the `.pem` path. `_import_private_key`
  reads the key at import time. Without a key, the API returns only the publishable
  fields.

## Form contract

`src/datasure/surveycto/` was adapted from surveycto_python_dict (`d6f54f9`) and is
DataSure's own code: change it here. Upstream changes are not copied over.

## Tests

- `tests/connectors/test_scto.py` mocks `SurveyCTOAPIClient`. `TestTypedImport`
  drives the import with the synthetic farm form,
  `tests/surveycto/farm_form.py` (`XML`, `ROWS`).
- `tests/utils/test_scto_api.py` patches `_make_request` or `session.get`.
- `tests/surveycto/` holds the contract, xpath and cast tests, adapted from
  upstream.
