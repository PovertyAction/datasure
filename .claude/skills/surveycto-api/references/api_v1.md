# SurveyCTO Server API v1 Reference

Base URL: `https://{server_name}.surveycto.com/api/v1`

Authentication: HTTP Basic Auth

---

## Forms

### Download CSV data in long format

```http
GET /api/v1/forms/data/csv/{formId}
```

Downloads form data as CSV in long format. No data truncation. One file per repeat group (use `/api/v1/forms/files/csv/{formId}` to get all URLs).

#### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `reviewStatuses` | string | No | Comma-separated filter: `approved`, `rejected` |
| `asAttachment` | boolean | No | Download as file attachment. Default: `false` |

**Response:** `200 text/csv`

---

### Download CSV data for a specific repeat group

```http
GET /api/v1/forms/data/csv/{formId}/{repeatGroupName}
```

Downloads CSV data for a single repeat group from a form in long format.

#### Path Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `formId` | Yes | Form identifier |
| `repeatGroupName` | Yes | Name of the repeat group as defined in the form |

#### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `reviewStatuses` | string | No | Comma-separated filter: `approved`, `rejected` |
| `asAttachment` | boolean | No | Default: `false` |

**Response:** `200 text/csv`

---

### Download CSV data in wide format

```http
GET /api/v1/forms/data/wide/csv/{formId}
```

Downloads form data as a single CSV file. All repeat groups are represented as separate columns.

> **Warning:** Field data is **truncated at 16,384 characters**. Use long format or JSON format for complete data.

#### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `reviewStatuses` | string | No | Comma-separated filter: `approved`, `rejected` |
| `asAttachment` | boolean | No | Default: `false` |

**Response:** `200 text/csv`

---

### Download JSON data in wide format

```http
GET /api/v1/forms/data/wide/json/{formId}
```

Downloads form data as JSON. No data truncation. Repeat groups are represented as nested arrays/objects.

#### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `asAttachment` | boolean | No | Default: `false` |
| `afterDateExclusive` | string | No | Only include submissions received after this date (incremental download) |
| `reviewStatuses` | string | No | Comma-separated filter: `approved`, `rejected` |

**Response:** `200 application/json`

> **Note:** In v2, JSON wide format requires the `date` parameter and is the preferred endpoint. Use v2 for new code.

---

### Retrieve long format data URLs

```http
GET /api/v1/forms/files/csv/{formId}
```

Returns a newline-delimited list of URLs for all long-format CSV files for a form (one URL for the main data file, one per repeat group). Use these URLs to download the individual CSV files.

In the CSV files, group names are prefixed to field names separated by hyphens (e.g., `group1-group2-field1`).

**Response:** `200 text/plain` — newline-delimited list of URLs

---

## Server Configuration

### Configure CSV linebreak replacement

```http
POST /api/v1/forms/settings/csv/linebreak?v={character}
```

Sets a server-wide replacement character for line breaks in CSV exports, preventing line breaks from being interpreted as new rows.

> **Important:** Only affects new incoming data. Set this before starting data collection.

#### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `v` | string | Yes | Replacement character for line breaks |

**Responses:** `200` Success, `400` Bad request, `401` Unauthorized, `403` Forbidden, `500` Server error

---

### Remove CSV linebreak replacement settings

```http
DELETE /api/v1/forms/settings/csv/linebreak
```

Removes the server-wide linebreak replacement setting. Line breaks will appear as actual line breaks in CSV exports going forward.

> **Important:** Only affects new incoming data. Change is permanent until reconfigured.

**Responses:** `200` No setting was configured, `401` Unauthorized, `403` Forbidden, `500` Server error
