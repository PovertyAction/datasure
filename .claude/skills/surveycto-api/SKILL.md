---
name: surveycto-api
description: Use this skill when working with the SurveyCTO API in this project — fetching form submissions, handling rate limits, encrypted forms, or credential configuration. Covers the pysurveycto client, fetch_submissions(), RateLimitError, and all related environment variables.
---

# SurveyCTO API Skill

This skill covers how the GiveWell VCS dashboard interacts with SurveyCTO to pull form submissions.

## Architecture overview

```text
.env (credentials)
  └─ src/utils/config_utils.py   load_credentials(), load_private_key_path()
       └─ src/connectors/scto.py  fetch_submissions() → pysurveycto.SurveyCTOObject
            └─ src/processing/processor.py  load_submissions() / append_submissions()
                 └─ data/submissions.duckdb  (local cache)
```

The connector layer is intentionally thin: it calls the SurveyCTO API and returns raw dicts. All caching, transformation, and querying happen downstream.

## Environment variables

| Variable | Required | Description |
| --- | --- | --- |
| `SURVEYCTO_SERVER` | Yes | Server name or full URL (`ipa3`, `https://ipa3.surveycto.com`) |
| `SURVEYCTO_USERNAME` | Yes | SurveyCTO account email |
| `SURVEYCTO_PASSWORD` | Yes | SurveyCTO account password |
| `SURVEYCTO_FORM_ID` | Yes | Form ID to pull submissions from |
| `SURVEYCTO_PRIVATE_KEY_PATH` | No | Path to PEM private key for encrypted forms |

All four required vars are loaded by `load_credentials()` in `src/utils/config_utils.py`. If any are missing it raises `OSError` with the missing variable names listed.

## Credential loading

```python
from src.utils.config_utils import load_credentials, load_private_key_path

server, username, password, form_id = load_credentials()
private_key_path = load_private_key_path()   # returns str | None
```

`load_private_key_path()` returns `None` if the env var is unset, empty, or points to a missing file — never raises.

## fetch_submissions()

**Location:** `src/connectors/scto.py`

```python
def fetch_submissions(
    server: str,
    username: str,
    password: str,
    form_id: str,
    since_date: date | None = None,
    private_key_path: str | None = None,
) -> list[dict]:
```

### Parameters

| Parameter | Type | Notes |
| --- | --- | --- |
| `server` | `str` | Bare name, URL, or full subdomain — normalised internally |
| `username` | `str` | SurveyCTO account email |
| `password` | `str` | SurveyCTO account password |
| `form_id` | `str` | Form ID as shown in SurveyCTO console |
| `since_date` | `date \| None` | Fetch only submissions on or after this date |
| `private_key_path` | `str \| None` | Path to PEM file for encrypted forms |

### Returns

A `list[dict]` where each dict is one submission row in SurveyCTO JSON wide format. Field names match the form's variable names. The submission key is stored under `"KEY"`.

### Server name normalisation

`_server_name()` strips scheme (`https://`, `http://`), `.surveycto.com` suffix, trailing slashes, and whitespace so any of these work equivalently:

```python
fetch_submissions("ipa3", ...)
fetch_submissions("https://ipa3.surveycto.com/", ...)
fetch_submissions("ipa3.surveycto.com", ...)
```

### Unencrypted form (default)

```python
records = fetch_submissions(server, username, password, form_id)
```

Uses `pysurveycto.SurveyCTOObject.get_form_data()` as a plain GET request.

### Encrypted form

```python
records = fetch_submissions(
    server, username, password, form_id,
    private_key_path="/path/to/private_key.pem",
)
```

When `private_key_path` is provided the PEM file is opened and passed as the `key=` argument to `get_form_data()`. SurveyCTO requires a multipart POST with the key attached for encrypted forms.

### Incremental pull (append mode)

```python
from src.processing.processor import latest_submission_date

since = latest_submission_date("data/submissions.duckdb")
records = fetch_submissions(server, username, password, form_id, since_date=since)
```

When `since_date` is `None`, a hardcoded epoch of `2026-04-01` is used as the lower bound so all submissions are returned.

## Rate limiting

SurveyCTO returns HTTP **417** when a rate limit is hit. The connector translates this into a `RateLimitError`:

```python
from src.connectors.scto import RateLimitError, fetch_submissions

try:
    records = fetch_submissions(server, username, password, form_id)
except RateLimitError as exc:
    print(f"Rate limited — {exc}")   # exc message is the wait instruction from SCTO
```

The 417 response body contains `{"error": {"message": "..."}}` with the wait time. All other `HTTPError` statuses are re-raised unchanged.

**Rate limit guidance:** SurveyCTO rate-limits bulk data pulls. If you hit a 417, wait the period specified in the error message before retrying. The app's "Refresh data" button surfaces this to the user via `st.warning`.

## pysurveycto client

The project uses the [`pysurveycto`](https://github.com/PovertyAction/pysurveycto) library:

```python
import pysurveycto

client = pysurveycto.SurveyCTOObject(server_name, username, password)
data = client.get_form_data(
    form_id,
    format="json",
    oldest_completion_date=datetime(2025, 1, 1),   # lower bound
    key=open("key.pem", "rb"),                      # only for encrypted forms
)
```

`get_form_data` returns a `list[dict]`. Each dict has string values for all fields.

## Adding new connector behaviour

If you need to extend the connector (e.g. pull a different data endpoint):

1. Add a new function to `src/connectors/scto.py` — keep it a thin wrapper around `pysurveycto`
2. All env-var loading belongs in `src/utils/config_utils.py`, not in the connector
3. The connector must never import from `src.processing` or `src.views` (no circular deps)
4. If the new function can rate-limit, raise `RateLimitError` on HTTP 417 the same way `fetch_submissions` does

## Common errors

| HTTP status | Meaning | Handler |
| --- | --- | --- |
| 401 | Bad credentials | Fix `SURVEYCTO_USERNAME` / `SURVEYCTO_PASSWORD` in `.env` |
| 403 | Permission denied | Ensure the account has access to the form |
| 404 | Form not found | Check `SURVEYCTO_FORM_ID` in `.env` |
| 417 | Rate limit | Caught as `RateLimitError`; wait and retry |
| 500 | Server error | Re-raised as `HTTPError`; usually transient |

## Testing the connector

Tests live in `tests/connectors/test_scto.py`. The client is mocked via `unittest.mock.patch`:

```python
with patch("src.connectors.scto.pysurveycto.SurveyCTOObject") as mock_cls:
    mock_cls.return_value.get_form_data.return_value = [{"KEY": "uuid:001"}]
    result = fetch_submissions("ipa3", "user", "pass", "form1")
```

To test the 417 path:

```python
from requests.exceptions import HTTPError

mock_response = MagicMock()
mock_response.status_code = 417
mock_response.json.return_value = {"error": {"message": "wait 60s"}}
mock_client.get_form_data.side_effect = HTTPError(response=mock_response)
```
