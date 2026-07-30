# Livora AI Frontend API Reference

Version: MVP backend as of 29 July 2026

This document replaces the legacy authentication, single-upload, insights, and
report-analysis documents. It describes the API contracts that the new
frontend should use.

## 1. Environments and global rules

### Base URLs

Local development:

```text
http://127.0.0.1:5000
```

The deployed base URL must be supplied through frontend environment
configuration. Do not hardcode it inside screen components.

### Content types

Use this header for JSON requests:

```http
Content-Type: application/json
```

Do not manually set `Content-Type` for multipart report uploads. The mobile
runtime must generate the multipart boundary.

### Authentication

Every endpoint is protected except:

- `GET /`
- `POST /auth/signup`
- `POST /auth/login`
- `POST /auth/refresh`

Protected requests require:

```http
Authorization: Bearer <access_token>
```

The authenticated user comes from the access token. Never include `user_id`
in protected request bodies, query parameters, or multipart form data.

### Token lifecycle

- Access tokens last 15 minutes.
- Refresh tokens last 30 days.
- Refresh tokens are single-use and rotate on every successful refresh.
- When a protected request returns `401`, call `POST /auth/refresh` once,
  replace both stored tokens, and retry the original request once.
- Concurrent `401` responses should share one refresh operation.
- If refresh fails, clear both tokens and return the user to sign-in.
- Keep the same report-upload idempotency key when retrying after token
  refresh.

Store tokens using platform-secure storage. Do not log passwords, access
tokens, refresh tokens, report contents, or medical responses.

### Standard error shape

Most failures use:

```json
{
  "success": false,
  "error": "Human-readable error message"
}
```

Common status codes:

| Status | Meaning |
|---|---|
| `400` | Invalid request, field, query value, or identifier |
| `401` | Access token missing, expired, invalid, or revoked |
| `403` | Authenticated user is not allowed to access the resource |
| `404` | User, report, or conversation was not found |
| `409` | Conflict, duplicate account, context mismatch, or upload replay conflict |
| `413` | Multipart upload is larger than the configured request limit |
| `422` | Report cannot be processed or onboarding information is incomplete |
| `429` | Authentication rate limit reached |
| `500` | Unexpected backend failure |
| `503` | Authentication or AI provider is unavailable |

An authentication rate-limit response also contains `retry_after` in seconds
and a `Retry-After` response header:

```json
{
  "success": false,
  "error": "Too many attempts. Please try again later.",
  "retry_after": 900
}
```

### Missing values and trends

- Missing values are JSON `null`, not zero and not `"N/A"`.
- Dashboard numeric trends use signed percentages such as `"+4.2%"`.
- An unchanged dashboard trend is an empty string: `""`.
- Report-analysis trends use text such as `"12% decrease"` or `"stable"`.
- Timeline trends use `"+4.2%"`, `"-3%"`, `"stable"`, or `null`.
- Categorical test trends use `"changed"` or `"stable"`.
- Health scores are deterministic MVP wellness scores, not diagnostic scores.

## 2. Endpoint index

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/` | Backend health check |
| `POST` | `/auth/signup` | Create account and authentication session |
| `POST` | `/auth/login` | Sign in |
| `POST` | `/auth/refresh` | Rotate refresh token |
| `POST` | `/auth/logout` | Revoke current session |
| `GET` | `/auth/me` | Restore authenticated user |
| `POST` | `/onboarding` | Save medical and lifestyle profile |
| `GET` | `/dashboard` | Load dashboard |
| `GET` | `/recent-reports` | Load three most recent uploaded files |
| `POST` | `/report-batches` | Upload and process one or more reports |
| `GET` | `/report-documents/<document_id>/view-url` | Create a short-lived private report viewing URL |
| `POST` | `/report-analysis` | Load analysis for a saved report |
| `POST` | `/health-insights` | Load expanded health insights |
| `POST` | `/assistant/chat` | Start or continue assistant conversation |
| `GET` | `/timeline` | Load weekly, monthly, or yearly trends |
| `GET` | `/profile` | Load profile summary |
| `PATCH` | `/profile` | Update personal information |
| `POST` | `/help-support` | Submit a support ticket |

## 3. Authentication API

### 3.1 Create account

```http
POST /auth/signup
Content-Type: application/json
```

Request:

```json
{
  "full_name": "Naman Malik",
  "email": "naman@example.com",
  "password": "correct horse battery staple",
  "confirm_password": "correct horse battery staple",
  "terms_accepted": true
}
```

Validation:

- `full_name`: 2–100 characters after trimming.
- `email`: valid email address, maximum 254 characters.
- `password`: 15–128 characters and not one of the blocked common passwords.
- `confirm_password`: must equal `password`.
- `terms_accepted`: must be boolean `true`.

Success — `201 Created`:

```json
{
  "success": true,
  "user": {
    "user_id": 30,
    "full_name": "Naman Malik",
    "email": "naman@example.com",
    "age": null,
    "gender": null
  },
  "auth": {
    "access_token": "<jwt-access-token>",
    "refresh_token": "<rotating-refresh-token>",
    "token_type": "Bearer",
    "expires_in": 900,
    "access_expires_at": "2026-07-29T15:15:00+00:00",
    "refresh_expires_at": "2026-08-28T15:00:00+00:00"
  }
}
```

Relevant failures:

- `400`: invalid fields, password, confirmation, or terms.
- `409`: account cannot be created, including an existing email.
- `429`: signup rate limit reached.
- `503`: authentication secret is not configured.

`POST /signup` remains a temporary compatibility alias. New frontend code
should use `/auth/signup`.

### 3.2 Sign in

```http
POST /auth/login
Content-Type: application/json
```

Request:

```json
{
  "email": "naman@example.com",
  "password": "correct horse battery staple"
}
```

Success — `200 OK`:

```json
{
  "success": true,
  "user": {
    "user_id": 30,
    "full_name": "Naman Malik",
    "email": "naman@example.com",
    "age": 26,
    "gender": "male"
  },
  "auth": {
    "access_token": "<jwt-access-token>",
    "refresh_token": "<rotating-refresh-token>",
    "token_type": "Bearer",
    "expires_in": 900,
    "access_expires_at": "2026-07-29T15:15:00+00:00",
    "refresh_expires_at": "2026-08-28T15:00:00+00:00"
  }
}
```

Relevant failures:

- `400`: invalid email or missing password.
- `401`: invalid email or password.
- `429`: login rate limit reached.
- `503`: authentication service is not configured.

`POST /login` remains a temporary compatibility alias. New frontend code
should use `/auth/login`.

### 3.3 Refresh authentication

```http
POST /auth/refresh
Content-Type: application/json
```

Request:

```json
{
  "refresh_token": "<current-refresh-token>"
}
```

Success — `200 OK`:

```json
{
  "success": true,
  "auth": {
    "access_token": "<new-jwt-access-token>",
    "refresh_token": "<new-refresh-token>",
    "token_type": "Bearer",
    "expires_in": 900,
    "access_expires_at": "2026-07-29T15:30:00+00:00",
    "refresh_expires_at": "2026-08-28T15:15:00+00:00"
  }
}
```

The refresh token sent in the request is invalid after successful rotation.
The frontend must atomically replace both old tokens.

Failure — `401 Unauthorized`:

```json
{
  "success": false,
  "error": "Invalid or expired refresh token"
}
```

### 3.4 Sign out

```http
POST /auth/logout
Authorization: Bearer <access_token>
Content-Type: application/json
```

Request body:

```json
{}
```

Success — `200 OK`:

```json
{
  "success": true,
  "message": "Signed out"
}
```

Clear local access and refresh tokens after a successful logout.

### 3.5 Restore current user

```http
GET /auth/me
Authorization: Bearer <access_token>
```

Success — `200 OK`:

```json
{
  "success": true,
  "user": {
    "user_id": 30,
    "full_name": "Naman Malik",
    "email": "naman@example.com",
    "age": 26,
    "gender": "male"
  }
}
```

Use this endpoint when restoring an existing authenticated application
session.

## 4. Onboarding API

```http
POST /onboarding
Authorization: Bearer <access_token>
Content-Type: application/json
```

Request:

```json
{
  "age": 26,
  "gender": "male",
  "weight": 75,
  "height": 175,
  "diabetes_status": false,
  "hypertension": false,
  "previous_liver_disease": false,
  "family_history": true,
  "activity_level": "moderately active",
  "exercise_frequency": "2-4 times per week",
  "alcohol_consumption": "occasional",
  "smoking_status": "never"
}
```

Do not send `user_id`.

Validation:

| Field | Accepted values |
|---|---|
| `age` | Whole number from 13 through 120 |
| `gender` | `male`, `female`, `other` |
| `weight` | Number from 20 through 500 kg |
| `height` | Number from 80 through 250 cm |
| `diabetes_status` | Boolean; omitted value defaults to `false` |
| `hypertension` | Boolean; omitted value defaults to `false` |
| `previous_liver_disease` | Boolean; omitted value defaults to `false` |
| `family_history` | Boolean; omitted value defaults to `false` |
| `activity_level` | `sedentary`, `lightly active`, `moderately active`, `very active` |
| `exercise_frequency` | `never`, `1-2 times per week`, `2-4 times per week`, `5+ times every week`, `every day` |
| `alcohol_consumption` | Optional: `none`, `occasional`, `moderate`, `heavy` |
| `smoking_status` | Optional: `never`, `former`, `current` |

Success — `200 OK`:

```json
{
  "success": true,
  "message": "Onboarding completed"
}
```

Onboarding must be completed before `/report-batches`, because age is required
for FIB-4 calculation and the report snapshot.

## 5. Dashboard API

```http
GET /dashboard
Authorization: Bearer <access_token>
```

No request body is required.

Success — `200 OK`:

```json
{
  "success": true,
  "dashboard": {
    "first_name": "Naman",
    "health_score": {
      "score": 86,
      "status": "good",
      "trend": "+4 pts"
    },
    "latest_metrics": {
      "fib4": {
        "score": 1.08,
        "status": "normal",
        "trend": "-6.1%"
      },
      "apri": {
        "score": 0.31,
        "status": "normal",
        "trend": ""
      },
      "ast": {
        "score": 31,
        "status": "normal",
        "trend": "-8.8%"
      },
      "alt": {
        "score": 34,
        "status": "normal",
        "trend": "-12.8%"
      },
      "ggt": {
        "score": 29,
        "status": "normal",
        "trend": null
      },
      "bilirubin": {
        "score": 0.9,
        "status": "normal",
        "trend": "+12.5%"
      },
      "albumin": {
        "score": 4.3,
        "status": "normal",
        "trend": "+2.4%"
      },
      "platelets": {
        "score": 220,
        "status": "normal",
        "trend": "-2.2%"
      },
      "inr": {
        "score": 1,
        "status": "normal",
        "trend": ""
      },
      "pt": {
        "score": 12.5,
        "status": "normal",
        "trend": null
      },
      "afp": {
        "score": null,
        "status": null,
        "trend": null
      },
      "hbsag": {
        "score": "-ve",
        "status": "non-reactive",
        "trend": "changed"
      },
      "anti_hcv": {
        "score": null,
        "status": null,
        "trend": null
      },
      "ultrasound_prediction": {
        "score": "Normal",
        "status": "normal",
        "trend": "changed"
      }
    },
    "ai_insights": [
      {
        "insights_title": "ALT improving",
        "insights": "ALT has decreased and is currently within the expected range.",
        "insight_status": "normal"
      },
      {
        "insights_title": "Fibrosis markers stable",
        "insights": "The available fibrosis indicators remain in their expected categories.",
        "insight_status": "normal"
      },
      {
        "insights_title": "Recommended next step",
        "insights": "Continue routine follow-up testing to maintain trend history.",
        "insight_status": "info"
      }
    ],
    "upcoming": [
      {
        "upcoming_date": "14 Aug",
        "upcoming_title": "Liver function test"
      },
      {
        "upcoming_date": "02 Oct",
        "upcoming_title": "Coagulation profile"
      }
    ]
  }
}
```

Dashboard guarantees:

- `latest_metrics` always contains all 14 supported metrics.
- A metric without extracted data returns `score`, `status`, and `trend` as
  `null`.
- `ai_insights` always contains exactly three entries.
- `insight_status` is `normal`, `monitor`, or `info`.
- `upcoming` always contains the two earliest suggested tests.
- Health-score statuses are `good`, `fair`, `needs_attention`, or `high_risk`.
- Health-score trend compares the latest two saved report snapshots.
- Biomarker trends compare the two latest non-null values for that biomarker.
- Before the first upload, the endpoint still returns `200`: health score is
  based only on the available profile, biomarker fields are `null`, fallback
  insights are used, and upcoming tests are still supplied.

## 6. Recent Reports API

```http
GET /recent-reports
Authorization: Bearer <access_token>
```

Success — `200 OK`:

```json
{
  "success": true,
  "recent_reports": [
    {
      "report_type": "lft",
      "title": "Liver Function Test",
      "date_uploaded": "July 30, 2026",
      "document_id": "7288a44c-645d-49f7-bd94-da657ab9d08e",
      "report_id": 42,
      "filename": "sample_lft.pdf",
      "mime_type": "application/pdf",
      "size_bytes": 184512,
      "viewer_type": "pdf",
      "file_available": true
    },
    {
      "report_type": "cbc",
      "title": "Complete Blood Count",
      "date_uploaded": "July 30, 2026",
      "document_id": "0d2b2480-a56c-4ccb-85f2-4f27a34de156",
      "report_id": 42,
      "filename": "sample_cbc.pdf",
      "mime_type": "application/pdf",
      "size_bytes": 126981,
      "viewer_type": "pdf",
      "file_available": true
    },
    {
      "report_type": "ultrasound",
      "title": "Ultrasound Report",
      "date_uploaded": "July 20, 2026",
      "document_id": null,
      "report_id": null,
      "filename": null,
      "mime_type": null,
      "size_bytes": null,
      "viewer_type": null,
      "file_available": false
    }
  ]
}
```

The endpoint returns at most three uploaded files. Every file in a batch has
its own upload-history entry. A user with no uploads receives an empty
`recent_reports` array.

`date_uploaded` is a display string in `Month D, YYYY` format, such as
`July 30, 2026`.

Reports uploaded before private file storage was introduced have
`file_available: false`. The frontend must disable the open action for those
rows and may display `Original file unavailable`.

`GET /recent-reports/<user_id>` remains for compatibility but should not be
used by the new frontend.

### 6.1 Open an original report

Only request a viewing URL after the user taps a row whose
`file_available` value is `true`.

```http
GET /report-documents/7288a44c-645d-49f7-bd94-da657ab9d08e/view-url
Authorization: Bearer <access_token>
```

Success — `200 OK`:

```json
{
  "success": true,
  "document": {
    "document_id": "7288a44c-645d-49f7-bd94-da657ab9d08e",
    "report_id": 42,
    "report_type": "lft",
    "filename": "sample_lft.pdf",
    "mime_type": "application/pdf",
    "size_bytes": 184512,
    "viewer_type": "pdf",
    "url": "https://signed-private-url.example/...",
    "expires_in": 300,
    "expires_at": "2026-07-30T10:35:00+00:00"
  }
}
```

The URL grants temporary read access to that one private object. Do not save
or log it. Request a new URL on every tap, open it immediately in the
PDF/image viewer, and discard it when the viewer closes. The backend verifies
document ownership before issuing the URL.

Relevant failures:

- `404`: document does not exist or does not belong to the signed-in user.
- `503`: private document storage or URL generation is unavailable.

## 7. Batch Report Upload API

This endpoint replaces the old `/upload` followed by `/calculate` flow.

```http
POST /report-batches
Authorization: Bearer <access_token>
Idempotency-Key: <UUID>
Content-Type: multipart/form-data
```

Multipart fields:

| Field | Type | Required | Description |
|---|---|---|---|
| `files` | File, repeated | Yes | One through six report files |
| `report_types` | Text, repeated | Yes | Matching type for each file, in the same order |

Supported report types:

- `lft`
- `cbc`
- `coagulation`
- `afp`
- `hepatitis`
- `ultrasound`

Rules:

- Maximum six files per request.
- Only one file of each report type is allowed in a batch.
- Every `files` item must have one corresponding `report_types` item.
- Lab reports must be genuine PDF files.
- Ultrasound files must be genuine JPEG or PNG images.
- The default total multipart request limit is 20 MiB.
- Each file must yield at least one supported extracted value.
- The entire batch fails if any file fails.
- Failed batches do not create a report snapshot or upload-history rows.
- Successful files are retained in private object storage. Object keys and
  storage credentials are never returned by the API.
- Onboarding age must already be available.

Example logical multipart body:

```text
files         [sample_lft.pdf]
report_types  lft
files         [sample_cbc.pdf]
report_types  cbc
```

React Native pseudocode:

```ts
const form = new FormData();

selectedReports.forEach((item) => {
  form.append("files", {
    uri: item.uri,
    name: item.name,
    type: item.mimeType,
  } as any);
  form.append("report_types", item.reportType);
});

await fetch(`${baseUrl}/report-batches`, {
  method: "POST",
  headers: {
    Authorization: `Bearer ${accessToken}`,
    "Idempotency-Key": uploadAttemptId,
  },
  body: form,
});
```

Do not manually set the multipart `Content-Type` header.

New successful batch — `201 Created`:

```json
{
  "success": true,
  "batch": {
    "batch_id": "74d9a8b5-4128-41e1-af77-c26148a78077",
    "status": "completed",
    "file_count": 2,
    "files": [
      {
        "file_index": 0,
        "report_type": "lft",
        "status": "processed",
        "document_id": "7288a44c-645d-49f7-bd94-da657ab9d08e",
        "filename": "sample_lft.pdf",
        "mime_type": "application/pdf",
        "viewer_type": "pdf",
        "file_available": true,
        "extracted_fields": [
          "albumin",
          "alt",
          "ast",
          "ast_uln",
          "bilirubin",
          "ggt"
        ]
      },
      {
        "file_index": 1,
        "report_type": "cbc",
        "status": "processed",
        "document_id": "0d2b2480-a56c-4ccb-85f2-4f27a34de156",
        "filename": "sample_cbc.pdf",
        "mime_type": "application/pdf",
        "viewer_type": "pdf",
        "file_available": true,
        "extracted_fields": [
          "platelets"
        ]
      }
    ]
  },
  "report": {
    "report_id": 42,
    "calculated_metrics": {
      "fib4": {
        "value": 1.08,
        "status": "normal",
        "missing_inputs": []
      },
      "apri": {
        "value": 0.31,
        "status": "normal",
        "missing_inputs": []
      }
    },
    "biomarkers": {
      "ast": 31,
      "alt": 34,
      "ggt": 29,
      "bilirubin": 0.9,
      "albumin": 4.3,
      "platelets": 220,
      "inr": null,
      "pt": null,
      "afp": null,
      "hbsag": null,
      "anti_hcv": null,
      "ultrasound_prediction": null
    }
  }
}
```

If APRI or FIB-4 cannot be calculated, its `value` and `status` are `null`,
and `missing_inputs` identifies the missing fields:

```json
{
  "value": null,
  "status": null,
  "missing_inputs": [
    "ast_uln"
  ]
}
```

### Idempotency behavior

Generate one UUID when the user starts a logical upload attempt.

Reuse the same UUID for:

- Network timeout retries.
- Retrying after automatic access-token refresh.
- Accidental duplicate submission.
- Re-sending the exact same unchanged batch.

Use a new UUID when:

- The user changes the selected files.
- The user intentionally starts another upload.
- The previous batch failed and the user retries after correcting the issue.

Replaying a completed batch with the same key returns `200 OK` and the
original response with:

```json
{
  "idempotent_replay": true
}
```

Relevant failures:

- `400`: invalid UUID, missing files, invalid type, duplicate type, mismatched
  lists, invalid extension, or invalid file signature.
- `401`: access token required.
- `409`: the same key is processing or belongs to a previously failed batch.
- `413`: request exceeds upload-size limit.
- `422`: onboarding is incomplete or a file yields no supported values.
- `500`: extraction, model, database, or unexpected processing failure.

After success, use `report.report_id` with `/report-analysis` and
`/health-insights`.

## 8. Report Analysis API

Used by the Data Analysis screen.

```http
POST /report-analysis
Authorization: Bearer <access_token>
Content-Type: application/json
```

Request for a specific report:

```json
{
  "report_id": 42
}
```

`report_id` is optional. An empty object selects the latest saved report:

```json
{}
```

The selected report must belong to the authenticated user.

Success — `200 OK`:

```json
{
  "success": true,
  "report_analysis": {
    "health_score": 86,
    "health_status": "Good",
    "health_score_trend": "4 pts higher than last report",
    "risk_level": {
      "value": 14,
      "label": "Low",
      "band": 1,
      "scale_min": 0,
      "scale_max": 100
    },
    "biomarkers": {
      "fib4": {
        "value": 1.08,
        "trend": "6.1% decrease",
        "status": "normal",
        "insight": "Your FIB-4 result is within the expected range in the current report."
      },
      "apri": {
        "value": 0.31,
        "trend": "stable",
        "status": "normal",
        "insight": "Your APRI result is within the expected range in the current report."
      },
      "ast": {
        "value": 31,
        "trend": "8.8% decrease",
        "status": "normal",
        "insight": "AST is within the normal range and does not currently suggest liver inflammation."
      },
      "alt": {
        "value": 34,
        "trend": "12.8% decrease",
        "status": "normal",
        "insight": "ALT has improved and is currently within the expected range."
      },
      "ggt": {
        "value": 29,
        "trend": null,
        "status": "normal",
        "insight": "Your GGT result is within the expected range in the current report."
      },
      "bilirubin": {
        "value": 0.9,
        "trend": "12.5% increase",
        "status": "normal",
        "insight": "Your Bilirubin result is within the expected range in the current report."
      },
      "albumin": {
        "value": 4.3,
        "trend": "2.4% increase",
        "status": "normal",
        "insight": "Your Albumin result is within the expected range in the current report."
      },
      "platelets": {
        "value": 220,
        "trend": "2.2% decrease",
        "status": "normal",
        "insight": "Your Platelets result is within the expected range in the current report."
      },
      "inr": {
        "value": 1,
        "trend": "stable",
        "status": "normal",
        "insight": "Your INR result is within the expected range in the current report."
      },
      "pt": {
        "value": null,
        "trend": null,
        "status": null,
        "insight": null
      },
      "afp": {
        "value": null,
        "trend": null,
        "status": null,
        "insight": null
      },
      "hbsag": {
        "value": "-ve",
        "trend": "stable",
        "status": "non-reactive",
        "insight": "Your HBsAg result is within the expected range in the current report."
      },
      "anti_hcv": {
        "value": null,
        "trend": null,
        "status": null,
        "insight": null
      },
      "ultrasound_prediction": {
        "value": "Normal",
        "trend": "changed",
        "status": "normal",
        "insight": "Your Ultrasound result is within the expected range in the current report."
      }
    },
    "ai_summary": "Overall liver health appears stable. Continue healthy lifestyle habits and routine monitoring, and review the results with your clinician.",
    "report_id": 42
  }
}
```

Guarantees:

- `biomarkers` always contains all 14 supported metrics.
- A missing metric returns all four properties as `null`.
- Biomarker values come only from the selected current report snapshot.
- Trends compare the selected report with the immediately preceding report.
- `health_score_trend` is `null` when there is no prior report and `"stable"`
  when the score is unchanged.
- Health statuses are `Healthy`, `Good`, `Needs Monitoring`, `Concerning`, or
  `Critical`.
- Risk labels are `Low`, `Low Moderate`, `Moderate`, `High Moderate`, or
  `High`.
- The numeric risk value is suitable for a 0–100 slider.
- AI narrative is cached by report and analysis version.

Failure when no saved report exists — `404 Not Found`:

```json
{
  "success": false,
  "error": "No saved report found for this user"
}
```

## 9. Health Insights API

Used by the AI Health Insights screen.

```http
POST /health-insights
Authorization: Bearer <access_token>
Content-Type: application/json
```

Request:

```json
{
  "report_id": 42
}
```

`report_id` is optional. `{}` selects the latest saved report.

Success — `200 OK`:

```json
{
  "success": true,
  "health_insights": {
    "health_score": 86,
    "health_score_status": "Good",
    "health_score_summary": "Your liver health score has improved since the last report. Continue your current healthy habits.",
    "current_health_status": [
      "Low liver risk",
      "Stable biomarkers",
      "Normal albumin",
      "No critical findings"
    ],
    "biomarker_clinical_insights": {
      "fib4": {
        "score": 1.08,
        "status": "normal",
        "summary": "Your FIB-4 result is within the expected range in the current report."
      },
      "apri": {
        "score": 0.31,
        "status": "normal",
        "summary": "Your APRI result is within the expected range in the current report."
      },
      "ast": {
        "score": 31,
        "status": "normal",
        "summary": "AST is within the normal range and does not currently suggest liver inflammation."
      },
      "alt": {
        "score": 34,
        "status": "normal",
        "summary": "ALT has improved and is currently within the expected range."
      },
      "ggt": {
        "score": 29,
        "status": "normal",
        "summary": "Your GGT result is within the expected range in the current report."
      },
      "bilirubin": {
        "score": 0.9,
        "status": "normal",
        "summary": "Your Bilirubin result is within the expected range in the current report."
      },
      "albumin": {
        "score": 4.3,
        "status": "normal",
        "summary": "Your Albumin result is within the expected range in the current report."
      },
      "platelets": {
        "score": 220,
        "status": "normal",
        "summary": "Your Platelets result is within the expected range in the current report."
      },
      "inr": {
        "score": 1,
        "status": "normal",
        "summary": "Your INR result is within the expected range in the current report."
      },
      "pt": {
        "score": null,
        "status": null,
        "summary": null
      },
      "afp": {
        "score": null,
        "status": null,
        "summary": null
      },
      "hbsag": {
        "score": "-ve",
        "status": "non-reactive",
        "summary": "Your HBsAg result is within the expected range in the current report."
      },
      "anti_hcv": {
        "score": null,
        "status": null,
        "summary": null
      },
      "ultrasound_prediction": {
        "score": "Normal",
        "status": "normal",
        "summary": "Your Ultrasound result is within the expected range in the current report."
      }
    },
    "positive_changes": [
      {
        "title": "ALT improved 12.8%",
        "subtitle": "vs last report"
      },
      {
        "title": "Health score increased",
        "subtitle": "+4 points"
      },
      {
        "title": "Consistent monitoring",
        "subtitle": "4 reports tracked"
      },
      {
        "title": "Albumin within range",
        "subtitle": "Current report"
      }
    ],
    "risk_factors": [
      {
        "title": "No major recorded risks",
        "subtitle": "Maintain routine monitoring"
      }
    ],
    "areas_to_monitor": [
      "Biomarker Trends",
      "Follow-up Testing",
      "Healthy Lifestyle",
      "Routine Monitoring"
    ],
    "recommendation": "Your overall liver health status is good. Continue routine biomarker monitoring. Maintain physical activity and healthy nutrition. Schedule follow-up testing according to your clinician's advice."
  }
}
```

Guarantees:

- `current_health_status` contains four short strings.
- `biomarker_clinical_insights` contains all 14 metrics.
- `positive_changes` contains four title/subtitle pairs.
- `risk_factors` contains between one and four title/subtitle pairs.
- `areas_to_monitor` contains four short strings.
- Missing biomarker score, status, and summary values are `null`.
- The endpoint reuses the report-analysis calculations and cached narrative.

Like report analysis, this endpoint returns `404` if no saved report exists.

## 10. AI Health Assistant API

```http
POST /assistant/chat
Authorization: Bearer <access_token>
Content-Type: application/json
```

Message requirements:

- `message` is required.
- It must be a string containing non-whitespace text.
- Maximum length is 2,000 characters.

### 10.1 Start using a specific report

```json
{
  "report_id": 42,
  "message": "Is my ALT improving?"
}
```

### 10.2 Start using the latest report

Omit `report_id`:

```json
{
  "message": "What do my recent results mean?"
}
```

If the user has at least one report, the latest report is selected.

### 10.3 Start without any uploaded report

Use the same request and omit `report_id`:

```json
{
  "message": "What habits can support liver health?"
}
```

The assistant receives available profile information, an empty biomarker
context, and `context_report_id: null`. It can provide general educational
guidance but must not invent personal results.

### 10.4 Continue a conversation

```json
{
  "conversation_id": "fae67f3f-bb16-4bc1-98cf-654d6018af24",
  "message": "What should I ask my doctor?"
}
```

Do not change `report_id` in an existing conversation. The report context is
fixed when the conversation starts. To use a newly uploaded report, start a
new conversation without the old `conversation_id`.

Success — `200 OK`:

```json
{
  "success": true,
  "assistant": {
    "conversation_id": "fae67f3f-bb16-4bc1-98cf-654d6018af24",
    "created_new_conversation": true,
    "context_report_id": 42,
    "reply": "Your ALT is currently within the expected range and has decreased since the previous report.",
    "requires_urgent_care": false
  }
}
```

For a reportless conversation:

```json
{
  "success": true,
  "assistant": {
    "conversation_id": "0b704613-fe7f-47ef-8871-d25683302764",
    "created_new_conversation": true,
    "context_report_id": null,
    "reply": "General educational response based on the available information.",
    "requires_urgent_care": false
  }
}
```

Relevant failures:

- `400`: invalid report ID, missing message, oversized message, or invalid
  conversation ID.
- `404`: user, report, or conversation was not found.
- `409`: an attempt was made to change the report inside a conversation.
- `503`: health-assistant provider is unavailable.

## 11. Health Timeline API

```http
GET /timeline?period=weekly
Authorization: Bearer <access_token>
```

Supported values:

- `weekly`
- `monthly`
- `yearly`

If `period` is omitted, the backend defaults to `weekly`.

Success — `200 OK`, shortened weekly example:

```json
{
  "success": true,
  "timeline": {
    "selected_period": "weekly",
    "health_score": 88,
    "health_trend": "+4.8%",
    "trend_summary": "Liver health score improved by 4 points since last week.",
    "trend_sub_summary": "Biomarkers are improving and remain within expected ranges.",
    "biomarkers": {
      "fib4": {
        "value": 1.08,
        "trend": "-6.1%"
      },
      "apri": {
        "value": 0.31,
        "trend": "stable"
      },
      "ast": {
        "value": 31,
        "trend": "-8.8%"
      },
      "alt": {
        "value": 34,
        "trend": "-12.8%"
      },
      "ggt": {
        "value": 29,
        "trend": null
      },
      "bilirubin": {
        "value": 0.9,
        "trend": "+12.5%"
      },
      "albumin": {
        "value": 4.3,
        "trend": "+2.4%"
      },
      "platelets": {
        "value": 220,
        "trend": "-2.2%"
      },
      "inr": {
        "value": 1,
        "trend": "stable"
      },
      "pt": {
        "value": null,
        "trend": null
      },
      "afp": {
        "value": null,
        "trend": null
      },
      "hbsag": {
        "value": "-ve",
        "trend": "stable"
      },
      "anti_hcv": {
        "value": null,
        "trend": null
      },
      "ultrasound_prediction": {
        "value": "Normal",
        "trend": "changed"
      }
    },
    "health_history": [
      {
        "period": "Week 1",
        "label": "06 Jul",
        "start_date": "2026-07-06",
        "end_date": "2026-07-12",
        "health_score": 82,
        "biomarkers": {
          "ast": {
            "value": 38,
            "trend": null
          },
          "alt": {
            "value": 44,
            "trend": null
          },
          "bilirubin": {
            "value": 0.8,
            "trend": null
          },
          "albumin": {
            "value": 4.2,
            "trend": null
          },
          "ggt": {
            "value": 31,
            "trend": null
          }
        }
      },
      {
        "period": "Week 4",
        "label": "27 Jul",
        "start_date": "2026-07-27",
        "end_date": "2026-08-02",
        "health_score": 88,
        "biomarkers": {
          "ast": {
            "value": 31,
            "trend": "-8.8%"
          },
          "alt": {
            "value": 34,
            "trend": "-12.8%"
          },
          "bilirubin": {
            "value": 0.9,
            "trend": "+12.5%"
          },
          "albumin": {
            "value": 4.3,
            "trend": "+2.4%"
          },
          "ggt": {
            "value": 29,
            "trend": null
          }
        }
      }
    ]
  }
}
```

The actual weekly response always contains four history items, including empty
periods. The shortened example above omits Week 2 and Week 3 only for
readability.

Timeline behavior:

- `health_score` is the best score recorded in the current selected period.
- `health_trend`, text summaries, top-level biomarker trends, and history
  trends use the latest report in each calendar period.
- Weekly history contains the current week and previous three weeks.
- Monthly history contains January through December of the current year.
- Yearly history contains every year that has saved report data.
- Top-level `biomarkers` contains all 14 metrics.
- Each history entry contains AST, ALT, bilirubin, albumin, and GGT.
- Missing periods and unavailable comparisons return `null`.
- The endpoint still returns `200` without reports. Weekly and monthly history
  use empty periods; yearly history is an empty array.

Invalid period — `400 Bad Request`:

```json
{
  "success": false,
  "error": "period must be weekly, monthly, or yearly"
}
```

## 12. Profile API

### 12.1 Load profile

```http
GET /profile
Authorization: Bearer <access_token>
```

Success — `200 OK`:

```json
{
  "success": true,
  "profile": {
    "full_name": "Naman Malik",
    "age": 26,
    "gender": "male",
    "health_score": 86,
    "total_uploaded_reports": 7,
    "liver_health_status": "Healthy",
    "biomarkers_status": "Stable",
    "month_year": "July 2026"
  }
}
```

Possible liver-health statuses:

- `Healthy`
- `Needs Improvement`
- `At Risk`
- `Critical`

Possible biomarker statuses:

- `Stable`
- `Monitor`
- `Critical`

`total_uploaded_reports` counts uploaded files, not report batches. When no
saved biomarker report exists, the endpoint returns the profile-based health
score and `Monitor` for `biomarkers_status`.

### 12.2 Update personal information

```http
PATCH /profile
Authorization: Bearer <access_token>
Content-Type: application/json
```

Request may contain one or more fields:

```json
{
  "full_name": "Updated Name",
  "age": 27,
  "gender": "other"
}
```

Validation:

- Only `full_name`, `age`, and `gender` are accepted.
- `full_name`: 2–100 characters after normalization.
- `age`: whole number from 13 through 120.
- `gender`: `male`, `female`, or `other`.
- Omitted fields remain unchanged.

Success — `200 OK`:

```json
{
  "success": true,
  "message": "Profile updated",
  "profile": {
    "full_name": "Updated Name",
    "age": 27,
    "gender": "other",
    "health_score": 86,
    "total_uploaded_reports": 7,
    "liver_health_status": "Healthy",
    "biomarkers_status": "Stable",
    "month_year": "July 2026"
  }
}
```

## 13. Help and Support API

```http
POST /help-support
Authorization: Bearer <access_token>
Content-Type: application/json
```

Preferred request:

```json
{
  "subject": "Report Upload Query",
  "description": "My coagulation report is not being accepted."
}
```

Accepted subjects:

- `Application Issue`
- `Report Upload Query`
- `AI Health Assessment Explanation`
- `Other Support Query`

The frontend screenshot value `Other Support Queries` is also accepted and is
stored as `Other Support Query`.

`message` is accepted as an alias for `description`:

```json
{
  "subject": "Application Issue",
  "message": "The application closes when I open the timeline."
}
```

Do not send both `description` and `message`. The submitted text must contain
non-whitespace content and may contain at most 4,000 characters.

Success — `201 Created`:

```json
{
  "success": true,
  "message": "Support request submitted",
  "ticket": {
    "ticket_id": 17,
    "subject": "Report Upload Query",
    "status": "open",
    "created_at": "2026-07-29T09:30:00+00:00"
  }
}
```

The MVP endpoint saves the ticket in PostgreSQL. It does not yet send email or
forward the ticket to an external help-desk platform.

## 14. Biomarker reference

| API key | Display name | Unit | Common statuses |
|---|---|---|---|
| `fib4` | FIB-4 | None | `normal`, `borderline`, `elevated` |
| `apri` | APRI | None | `normal`, `borderline`, `elevated` |
| `ast` | AST | U/L | `normal`, `elevated` |
| `alt` | ALT | U/L | `normal`, `elevated` |
| `ggt` | GGT | U/L | `normal`, `elevated` |
| `bilirubin` | Bilirubin | mg/dL | `low`, `normal`, `elevated` |
| `albumin` | Albumin | g/dL | `low`, `normal`, `elevated` |
| `platelets` | Platelets | 10^9/L | `low`, `normal`, `elevated` |
| `inr` | INR | None | `low`, `normal`, `elevated` |
| `pt` | Prothrombin time | seconds | `low`, `normal`, `elevated` |
| `afp` | AFP | ng/mL | `normal`, `elevated` |
| `hbsag` | HBsAg | None | `non-reactive`, `reactive` |
| `anti_hcv` | Anti-HCV | None | `non-reactive`, `reactive` |
| `ultrasound_prediction` | Ultrasound | None | `normal`, `abnormal` |

The frontend should display values supplied by the API without recalculating
clinical status thresholds.

For both `hbsag` and `anti_hcv`, response values are `-ve` or `+ve`, and
statuses are `non-reactive` or `reactive`. The backend continues to store
these categorical results internally as numeric flags.

## 15. Deprecated and compatibility endpoints

Do not use these for new frontend work:

| Endpoint | Status | Replacement |
|---|---|---|
| `POST /signup` | Temporary alias | `POST /auth/signup` |
| `POST /login` | Temporary alias | `POST /auth/login` |
| `POST /upload` | Legacy single-file flow | `POST /report-batches` |
| `POST /calculate` | Legacy calculation step | Calculations occur in `/report-batches` |
| `POST /insights` | Older generalized analysis | `GET /dashboard` and `POST /health-insights` |
| `GET /recent-reports/<user_id>` | Compatibility route | `GET /recent-reports` |

## 16. Recommended frontend screen mapping

| Frontend screen | API calls |
|---|---|
| Signup | `POST /auth/signup` |
| Sign-in | `POST /auth/login` |
| Application restore | `POST /auth/refresh` when needed, then `GET /auth/me` |
| Onboarding | `POST /onboarding` |
| Dashboard | `GET /dashboard` |
| Report Upload | `GET /recent-reports`, `POST /report-batches`, then `GET /report-documents/<document_id>/view-url` on tap |
| Data Analysis | `POST /report-analysis` using returned `report_id` |
| AI Health Insights | `POST /health-insights` using the same `report_id` |
| AI Health Assistant | `POST /assistant/chat` |
| Progress Timeline | `GET /timeline?period=weekly|monthly|yearly` |
| Profile | `GET /profile`, `PATCH /profile` |
| Help and Support | `POST /help-support` |

## 17. Required upload-to-analysis flow

1. User chooses one or more report files and assigns each report type.
2. Frontend generates one UUID for the logical upload attempt.
3. Frontend calls `POST /report-batches`.
4. On `401`, frontend refreshes authentication once and retries the upload
   using the same UUID.
5. On `201` or idempotent `200`, frontend reads `report.report_id`.
6. Frontend calls `POST /report-analysis` with that report ID.
7. The same report ID may be used for `/health-insights` and to start a
   report-specific `/assistant/chat` conversation.
8. Dashboard, recent reports, profile, and timeline can then be refreshed.
9. To open an original upload later, read its `document_id` from
   `/recent-reports`, request its `/view-url`, and pass the returned temporary
   URL to the PDF/image viewer.
