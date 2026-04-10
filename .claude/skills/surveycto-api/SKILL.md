---
name: surveycto-api
description: This skill should be used when working with the SurveyCTO Server API (v1 or v2) in this project. Use this skill when adding, modifying, or debugging API calls to SurveyCTO, extending SurveyCTOAPIClient or SCTOConnector, writing tests for SurveyCTO API interactions, or reasoning about endpoints, authentication, rate limits, encryption, and pagination patterns.
---

# SurveyCTO API Skill

## Overview

This skill provides guidance for working with the SurveyCTO Server API within this project. All API communication goes through `src/edms_scto_pipeline/utils/scto_api.py` (`SurveyCTOAPIClient`) and `src/edms_scto_pipeline/connectors/scto_connector.py` (`SCTOConnector`). The `pysurveycto` library is intentionally not used.

## Authentication

All endpoints use **HTTP Basic Auth** (username + password). The `SurveyCTOAPIClient` sets this up via `requests.Session` with `HTTPBasicAuth`.

**Exception — CSRF-protected endpoints** (form listing, form design download): These internal console endpoints require a two-step CSRF token flow handled by `_get_csrf_auth_headers()`:

1. HEAD request to base URL with `X-OpenRosa-Version: 1.0` to obtain the initial CSRF token
2. POST to `/login` using that token to obtain a refreshed CSRF token
3. All subsequent requests include `X-csrf-token` and `X-OpenRosa-Version: 1.0` headers

## Base URLs

| API Version | Base URL |
|-------------|----------|
| v1 | `https://{server_name}.surveycto.com/api/v1` |
| v2 | `https://{server_name}.surveycto.com/api/v2` |
| Console (CSRF) | `https://{server_name}.surveycto.com` |

## Project Client: `SurveyCTOAPIClient`

Located at `src/edms_scto_pipeline/utils/scto_api.py`. All HTTP calls go through `_make_request()` which handles error wrapping into `SurveyCTOAPIError`.

### Currently implemented methods

| Method | Endpoint | Notes |
|--------|----------|-------|
| `list_datasets()` | `GET /api/v2/datasets` | |
| `get_dataset_info(dataset_id)` | `GET /api/v2/datasets/{id}` | |
| `update_dataset(dataset_id, ...)` | `PUT /api/v2/datasets/{id}` | |
| `download_dataset_csv(dataset_id)` | `GET /api/v2/datasets/data/csv/{id}` | streams bytes |
| `upload_dataset_csv(dataset_id, csv_data)` | POST multipart to `/api/v2/datasets/data/csv/{id}` | replaces all data |
| `list_form_ids()` | `GET /api/v2/forms/ids` | |
| `list_forms()` | Console endpoint (CSRF) | returns `forms` key |
| `download_form_definition(form_id)` | Console form design endpoint (CSRF) | |
| `download_form_data_json(form_id, ...)` | `GET /api/v2/forms/data/wide/json/{id}` | POST when encrypted |
| `download_attachment_from_url(url, ...)` | Full URL from submission data | GET or POST with key |

### Adding new API methods

To add a method to `SurveyCTOAPIClient`:

1. Use `self._make_request(method, endpoint, params=..., json_data=..., stream=...)` for standard v2 endpoints
2. Use the CSRF pattern (see `list_forms`) for console/internal endpoints
3. Wrap non-`_make_request` calls in the same try/except pattern with specific exception types
4. Raise `SurveyCTOAPIError` with a descriptive message

## Key API Behaviours to Know

### Data Format & Truncation

- **CSV long format** (`/api/v1/forms/data/csv/{id}`): No truncation, multiple files (one per repeat group)
- **CSV wide format** (`/api/v1/forms/data/wide/csv/{id}`): **Truncates at 16,384 chars** — avoid for large text fields
- **JSON wide format** (`/api/v2/forms/data/wide/json/{id}`): No truncation, preferred for programmatic use; **requires `date` query param** in v2

### Rate Limiting

- Max **30 requests per minute** per server
- `GET /api/v2/forms/data/wide/json/{id}` with `date=0` (all data) enforces a **5-minute quiet period** between calls
- `SCTOConnector.get_form_data()` adds a `time.sleep(2)` before each form request

### Encrypted Forms

- Provide the private key as bytes or string via the `private_key` parameter
- JSON download: POST multipart with `files={"private_key": key}` instead of GET
- Attachment download: POST multipart with `files={"private_key": key}` instead of GET
- If the server returns 500 on an encrypted-key request for an unencrypted form, retry without the key (see `SCTOConnector.get_form_data()`)

### Pagination (v2)

Cursor-based pagination applies to: datasets, records, groups, roles, users.

- Default page size: 20, max: 1000
- Use `nextCursor` from the response to fetch the next page
- `null` nextCursor means no more pages

### Date Filtering (v2 Forms)

The `date` query parameter is **required** for `GET /api/v2/forms/data/wide/json/{id}`:

- Unix timestamp in seconds (<=12 digits) or milliseconds (>=13 digits)
- Use `0` to get all data (triggers 5-min rate limit)
- In `SCTOConnector`, `oldest_date` is converted: `{"date": int(oldest_date.timestamp())}`

### Dataset Records vs. CSV Upload

The project currently uses the CSV upload endpoint (`upload_dataset_csv`). The v2 API also supports individual record CRUD via `/api/v2/datasets/{id}/record(s)` — use these when you need to add/update/delete specific rows without replacing the whole dataset.

## Common Error Codes

| Code | Meaning |
|------|---------|
| 401 | Authentication failed — check credentials |
| 403 | Insufficient permissions |
| 404 | Form/dataset not found |
| 417 | Rate limited — wait and retry |
| 500 | Server error (may indicate wrong private key for encrypted form) |

## References

For full endpoint specifications including all request/response fields:

- [`references/api_v1.md`](references/api_v1.md) — Server API v1 (forms data, CSV settings)
- [`references/api_v2.md`](references/api_v2.md) — Server API v2 (datasets, records, forms, submissions, groups, teams, roles, users)
