# SurveyCTO Server API v2 Reference

Base URL: `https://{server_name}.surveycto.com/api/v2`

Authentication: HTTP Basic Auth

Pagination: Cursor-based. Default page size: 20. Max: 1000. Use `nextCursor` from the response for the next page; `null` means no more pages.

---

## Datasets

### List all datasets

```http
GET /api/v2/datasets
```

Returns a paginated list of datasets the authenticated user can access.

#### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `cursor` | string | — | URL-encoded cursor from previous `nextCursor` |
| `limit` | integer | 20 | Page size (max 1000) |
| `orderBy` | string | `createdOn` | `id`, `title`, `createdOn`, `modifiedOn`, `status`, `version`, `discriminator` |
| `orderByDirection` | string | `ASC` | `ASC` or `DESC` |
| `teamId` | string | — | Filter by team ID |

**Response:** `200` Paginated list (`nextCursor`, `total`, `data[]`, `limit`)

---

### Create dataset

```http
POST /api/v2/datasets
Content-Type: application/json
```

#### Request Body Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique identifier (required) |
| `title` | string | Display title |
| `discriminator` | string | `CASES`, `ENUMERATORS`, or `DATA` |
| `allowOfflineUpdates` | boolean | Allow offline updates |
| `uniqueRecordField` | string | Field for unique record identification |
| `idFormatOptions` | object | ID format config for enumerator ID auto-generation |
| `casesManagementOptions` | object | Cases management configuration |
| `locationContext` | object | Group hierarchy positioning |

**Response:** `200` Dataset object (see Dataset Object below)

---

### Get single dataset

```http
GET /api/v2/datasets/{datasetId}
```

**Response:** `200` Dataset object, `401`, `403`, `404`, `500`

---

### Update dataset

```http
PUT /api/v2/datasets/{datasetId}
Content-Type: application/json
```

Only provided fields are updated. The `discriminator` cannot be changed after creation. `uniqueRecordField` cannot be updated if already set.

**Request Body:** Same fields as Create dataset (all optional).

**Response:** `200` Updated dataset object

---

### Delete dataset

```http
DELETE /api/v2/datasets/{datasetId}
```

Permanently deletes the dataset and all its data. Irreversible.

**Response:** `200 {"success": boolean, "message": string}`

---

### Purge dataset

```http
POST /api/v2/datasets/{datasetId}/purge
```

Clears all records but keeps the dataset structure and metadata intact.

**Response:** `200 {"success": boolean, "message": string}`

---

### Download dataset data as CSV

```http
GET /api/v2/datasets/data/csv/{datasetId}
```

Downloads all dataset rows and columns as UTF-8 encoded CSV.

#### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `asAttachment` | boolean | `false` | Download as file attachment |

**Response:** `200 text/csv`

---

### Dataset Object Schema

```json
{
  "id": "string",
  "title": "string",
  "discriminator": "CASES | ENUMERATORS | DATA",
  "status": "READY | DIRTY",
  "totalRecords": 0,
  "fieldNames": "comma,separated,field,names",
  "groupId": 0,
  "version": 0,
  "createdOn": "string",
  "modifiedOn": "string",
  "lastIncomingDataDate": "string",
  "allowOfflineUpdates": true,
  "uniqueRecordField": "string",
  "idFormatOptions": {},
  "casesManagementOptions": {}
}
```

`status` values:

- `READY` — data is synchronized and up-to-date
- `DIRTY` — currently synchronizing; data may be incomplete

---

## Dataset Records

All record endpoints require the dataset to have `uniqueRecordField` configured.

### Get single record

```http
GET /api/v2/datasets/{datasetId}/record?recordId={recordId}
```

**Response:** `200 {"recordId": "string", "modifiedAt": "string", "values": {}}`

---

### Update record

```http
PUT /api/v2/datasets/{datasetId}/record?recordId={recordId}
Content-Type: application/json
```

Updates an existing record. Only provided fields are updated. New fields are added as new columns.

**Request Body:** Key-value pairs of field names to string values.

**Response:** `200 {"recordId": "string", "modifiedAt": "string", "values": {}}`

---

### Delete record

```http
DELETE /api/v2/datasets/{datasetId}/record?recordId={recordId}
```

Permanently deletes the record. Irreversible.

**Response:** `200 {"success": boolean, "message": string}`

---

### Upsert record

```http
PATCH /api/v2/datasets/{datasetId}/record?recordId={recordId}
Content-Type: application/json
```

Updates an existing record or creates it if it doesn't exist. New fields added as new columns.

**Request Body:** Key-value pairs of field names to string values.

**Response:** `200 {"recordId": "string", "modifiedAt": "string", "values": {}}`

---

### Get all records from dataset

```http
GET /api/v2/datasets/{datasetId}/records
```

Paginated list of all records with optional filtering and sorting.

#### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `cursor` | string | — | Record ID as pagination cursor (URL-encode special chars) |
| `limit` | integer | 20 | Page size (max 1000) |
| `orderBy` | string | `modifiedAt` | Any field name or `modifiedAt` |
| `orderByDirection` | string | `ASC` | `ASC` or `DESC` |
| `modifiedAt.gt` | string | — | ISO 8601 timestamp; records modified after this (exclusive). Cannot combine with `modifiedAt.gte` |
| `modifiedAt.gte` | string | — | ISO 8601 timestamp; records modified on-or-after this. Cannot combine with `modifiedAt.gt` |
| `modifiedAt.lt` | string | — | ISO 8601 timestamp; records modified before this (exclusive). Cannot combine with `modifiedAt.lte` |
| `modifiedAt.lte` | string | — | ISO 8601 timestamp; records modified on-or-before this. Cannot combine with `modifiedAt.lt` |

**Response:** `200` Paginated list (`nextCursor`, `total`, `data[]`, `limit`)

---

### Add record to dataset

```http
POST /api/v2/datasets/{datasetId}/records
Content-Type: application/json
```

Creates a new record. For datasets with `uniqueRecordField`, the unique field value must be provided and must not already exist. Missing columns are added automatically.

**Request Body:** Key-value pairs of field names to string values.

**Response:** `200 {"recordId": "string", "modifiedAt": "string", "values": {}}`

---

### Upload records from CSV

```http
POST /api/v2/datasets/{datasetId}/records/upload
Content-Type: multipart/form-data
```

Bulk upload records from a CSV file (max 100MB).

#### Form Fields

| Field | Type | Description |
|-------|------|-------------|
| `file` | binary | CSV file |
| `metadata` | object | Upload configuration (mode, etc.) |

**Upload modes** (in `metadata`):

- `APPEND` — add new records
- `MERGE` — update existing records based on unique field
- `CLEAR` — replace all data

**Response:**

```json
{
  "rowsAdded": 0,
  "rowsUpdated": 0,
  "columnsAdded": 0,
  "valuesTruncated": 0,
  "errorMessages": [],
  "enumeratorDatasetLinkedMessage": "string"
}
```

> **Note:** Values are truncated at 255 characters by this endpoint.

---

## Forms

### Download form data as JSON (wide format)

```http
GET /api/v2/forms/data/wide/json/{formId}
```

Downloads all submission data as a JSON array. No data truncation. Repeat groups are nested structures.

> **Preferred endpoint for programmatic form data access.**

#### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `date` | string | **Yes** | Unix timestamp (seconds <=12 digits, ms >=13 digits) or URL-encoded date string. Use `0` for all data |
| `reviewStatuses` | string | No | Comma-separated filter: `approved`, `rejected` |
| `asAttachment` | boolean | No | Default: `false` |

> **Rate limit:** Requests with `date=0` enforce a **5-minute quiet period** between calls.

For encrypted forms, use POST with `files={"private_key": key_bytes}` and the same query parameters.

**Response:** `200 application/json` — array of submission objects

---

### List form IDs

```http
GET /api/v2/forms/ids
```

Returns all live form IDs (excludes drafts) the user can access.

#### Query Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `teamId` | string | Filter by team ID |

**Response:** `200 {"formIds": ["string"]}`

---

## Submissions

### Download submission attachment

```http
GET /api/v2/forms/{formId}/submissions/{instanceId}/attachments/{filename}
```

Downloads a specific attachment from a submission. Field values in JSON/CSV data contain URLs pointing to this endpoint — use those URLs directly or construct manually.

#### Path Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `formId` | Yes | Form identifier |
| `instanceId` | Yes | Submission KEY field value (e.g., `uuid:xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`) |
| `filename` | Yes | Exact filename from submission data. Do **not** include `.enc` extension for encrypted forms |

For encrypted form attachments, use POST with `multipart/form-data` body containing `private_key` file field. The private key is used for decryption and is not stored on the server.

**Response:** `200 */*` — file bytes

---

## Groups

### List groups

```http
GET /api/v2/groups
```

Paginated list of groups the authenticated user can access.

#### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `cursor` | integer | — | Group ID as pagination cursor |
| `limit` | integer | 20 | Page size (max 1000) |
| `orderBy` | string | `createdOn` | `id`, `title`, `createdOn` |
| `orderByDirection` | string | `ASC` | `ASC` or `DESC` |
| `parentGroupId` | integer | — | Filter to children of this parent group |

**Response:** `200` Paginated list, `400`, `401`, `403`, `500`

---

## Teams

### List team IDs

```http
GET /api/v2/teams/ids
```

Admin-only. Returns all team IDs, both active and paused by default.

#### Query Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `paused` | boolean | `true` = only paused, `false` = only active, omit = all |

**Response:** `200 {"teamIds": ["string"]}`, `401`, `403`, `500`

---

## Roles

### Get all roles

```http
GET /api/v2/roles
```

Paginated list of roles.

#### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `cursor` | string | — | Role ID as cursor (case-sensitive) |
| `limit` | integer | 20 | Page size (max 1000) |
| `orderBy` | string | `createdOn` | `id`, `title`, `createdOn`, `createdBy` |
| `orderByDirection` | string | `ASC` | `ASC` or `DESC` |

**Response:** `200` Paginated list, `400`, `401`, `403`, `500`

---

### Get role permissions

```http
GET /api/v2/roles/{roleId}
```

Returns detailed system-level and group-specific permissions for a role.

> **Note:** `roleId` is case-sensitive (e.g., `GLOBAL_ADMIN` not `global_admin`).

#### Query Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `groupId` | integer | Filter group permissions by specific group |

**Response:** `200` Role permissions object

---

## Users

### List all users

```http
GET /api/v2/users
```

Paginated list of users with optional role filtering.

#### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `cursor` | string | — | URL-encoded username as cursor |
| `limit` | integer | 20 | Page size (max 1000) |
| `orderBy` | string | `createdOn` | `username`, `roleId`, `createdOn`, `modifiedOn` |
| `orderByDirection` | string | `ASC` | `ASC` or `DESC` |
| `roleId` | string | — | Filter by role ID (case-sensitive) |

**Response:** `200` Paginated list, `400`, `401`, `403`, `500`

---

### Create user

```http
POST /api/v2/users
Content-Type: application/json
```

#### Request Body Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `username` | string | Yes | Unique username |
| `roleId` | string | Yes | Role to assign |
| `passwordOption` | string | Yes | `SET_NOW` or `USER_SET_OWN` |
| `password` | string | If `SET_NOW` | User password |
| `confirmPassword` | string | If `SET_NOW` | Must match `password` |
| `includePasswordInEmail` | boolean | No | Only valid when `passwordOption=SET_NOW` |

**Response:** `200 {"username": "string", "roleId": "string", "createdOn": "datetime", "modifiedOn": "datetime"}`

---

### Get user by username

```http
GET /api/v2/users/{username}
```

**Response:** `200` User object, `401`, `403`, `404`, `500`

---

### Update user

```http
PUT /api/v2/users/{username}
Content-Type: application/json
```

At least one of `password` or `roleId` must be provided.

#### Request Body Fields

| Field | Type | Description |
|-------|------|-------------|
| `roleId` | string | New role to assign |
| `password` | string | New password |
| `confirmPassword` | string | Required if `password` provided |

**Response:** `200` Updated user object

---

### Delete user

```http
DELETE /api/v2/users/{username}
```

Irreversible.

**Response:** `200 {"responseObject": "string", "code": 0, "message": "string"}`, `401`, `403`, `404`, `500`

---

### Bulk delete users

```http
DELETE /api/v2/users/bulk
Content-Type: application/json
```

Deletes multiple users. Duplicate usernames are automatically removed.

**Request Body:** `["username1", "username2", ...]`

**Response:**

```json
{
  "successful": ["string"],
  "failed": [{"username": "string", "error": "string"}],
  "summary": {}
}
```

---

### Bulk create users from JSON

```http
POST /api/v2/users/bulk/json
Content-Type: application/json
```

Creates up to 1000 users. Each item uses the same fields as single user creation.

**Request Body:** Array of user objects.

**Response:** `{"successful": [], "failed": [], "summary": {}}`

---

### Bulk update users from JSON

```http
PUT /api/v2/users/bulk/json?upsert={boolean}
Content-Type: application/json
```

Updates up to 1000 users. With `upsert=true`, creates users that don't exist.

#### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `upsert` | boolean | `false` | Create users if they don't exist |

**Request Body:** Array of user objects (same fields as single user update).

**Response:** `{"successful": [], "failed": [], "summary": {}}`

---

### Bulk create users from CSV file

```http
POST /api/v2/users/bulk/file
Content-Type: multipart/form-data
```

Creates users from a CSV file. Max 1MB, max 1000 users.

Required CSV headers: `username`, `roleId`
Optional CSV headers: `passwordOption`, `password`, `confirmPassword`, `includePasswordInEmail`

**Response:** `{"successful": [], "failed": [], "summary": {}}`

---

### Bulk update users from CSV file

```http
PUT /api/v2/users/bulk/file?upsert={boolean}
Content-Type: multipart/form-data
```

Updates users from a CSV file. Max 1000 users. With `upsert=true`, creates users that don't exist.

Required CSV headers: `username`
Optional CSV headers: `roleId`, `passwordOption`, `password`, `confirmPassword`, `includePasswordInEmail`

#### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `upsert` | boolean | `false` | Create users if they don't exist |

**Response:** `{"successful": [], "failed": [], "summary": {}}`
