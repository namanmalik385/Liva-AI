# 🩺 Livora AI — Liver Health Intelligence Platform
[![AMD ROCm Accelerated](https://img.shields.io/badge/AMD--ROCm-Accelerated-blue?logo=amd&logoColor=white&color=ED1C24)](https://www.amd.com/en/products/accelerators/rocm.html)
[![React Native](https://img.shields.io/badge/React%20Native-Expo%2057-61DAFB?logo=react&logoColor=white)](https://reactnative.dev/)
[![Flask API](https://img.shields.io/badge/Backend-Flask%203.0-000000?logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![TensorFlow Keras](https://img.shields.io/badge/ML%20Framework-TensorFlow%202.21-FF6F00?logo=tensorflow&logoColor=white)](https://www.tensorflow.org/)
[![Database](https://img.shields.io/badge/Database-PostgreSQL%20(Neon)-4169E1?logo=postgresql&logoColor=white)](https://neon.tech/)
[![Fireworks AI](https://img.shields.io/badge/LLM%20Host-Fireworks%20AI-9A3412)](https://fireworks.ai/)

**Livora AI** (sometimes referred to as Levora AI) is an intelligent, non-invasive liver disease screening and monitoring platform built for the **AMD Developer Hackathon Act II**. The platform combines a cross-platform mobile application, medical document parsing (OCR), deep learning-based ultrasound scan classification, clinical risk calculators, and Generative AI-driven personalized health recommendations to provide a unified portal for liver health tracking.


> **NOTE**
>
> **Repository Split Notice**
> This project is split into two repositories:
> 1. **This repository contains the backend code.**
> 2. The frontend mobile application repository can be found at **[Frontend Repository](https://github.com/ishaqashraf/levora-ai)** 

---

## 📖 Table of Contents

1. [Project Directory Flowchart](#-project-directory-flowchart)
2. [AI Models & AMD ROCm Optimization](#-ai-models--amd-rocm-optimization)
3. [API Route Specifications](#-api-route-specifications)
4. [System Prerequisites](#-system-prerequisites)
5. [Installation & Local Execution](#-installation--local-execution)
6. [Clinical Indices & Math](#-clinical-indices--math)
7. [Database Table Schema](#-database-table-schema)

---

## 🚨 Problem Statement & Solution

### The Problem
Liver diseases (such as Fatty Liver, Cirrhosis, Hepatitis, and Hepatocellular Carcinoma/HCC) represent a massive global health burden. Because the liver is a resilient organ, diseases are often **asymptomatic until late stages (fibrosis/cirrhosis)**. Regular screening is costly, requires complex clinical evaluations, and patients often struggle to interpret their blood test results or ultrasound imaging scans.

### The Solution
**Livora AI** democratizes liver health intelligence by offering:
*   **Instant Document Parsing**: Users upload standard Liver Function Tests (LFTs) or blood panels. The system automatically extracts key biomarkers using OCR and regular expressions.
*   **Computer Vision Imaging Classification**: Users scan and upload liver ultrasound images. An accelerated Keras CNN model running on the backend classifies the scan as HCC (liver cancer), Hemangioma (benign tumor), or Normal.
*   **Clinical Scoring**: Calculates standard clinical risk scores (FIB-4 and APRI indices) to evaluate liver fibrosis stages.
*   **GenAI Insights**: Leverages Fireworks AI Large Language Models to compile user lifestyle data, biomarkers, and scans into a single, cohesive medical explanation and actionable recommendations.

---

## 🗺️ Project Directory Flowchart

Below is a mind map/flowchart of the backend directory hierarchy detailing the purpose of key modules:

```mermaid
graph TD
    Root[📂 Livora-Ai]
    
    %% Top level grouping to prevent horizontal sprawl
    Root --> Core[⚙️ Core Services & Configuration]
    Root --> Logic[🧠 Logic, ML & Parsers]
    Root --> Web[🌐 Web Routing & Blueprints]
    
    %% Core branch
    Core --> App[📄 app.py <br> Flask entry point]
    Core --> DB[📄 db.py <br> PostgreSQL queries]
    Core --> LLM[📄 llm.py <br> Fireworks AI client]
    
    %% Logic branch
    Logic --> Calc[📁 calculators]
    Calc --> Calc1[📄 apri.py <br> APRI index]
    Calc --> Calc2[📄 fib4.py <br> FIB-4 index]
    
    Logic --> ML[📁 ml_models]
    ML --> Model[📄 best_model.h5 <br> MobileNetV2 weights]
    
    Logic --> Parsers[📁 parsers]
    Parsers --> P_all[📄 parsers/*.py <br> LFT/CBC/AFP/Hep/Coag]
    
    %% Web branch
    Web --> Routes[📁 routes]
    Routes --> R_all[📄 routes/*.py <br> Auth/Calculate/Insights/Upload]
    
    Web --> Services[📁 services]
    Services --> S1[📄 prompt_builder.py <br> Prompt construction]
    Services --> S2[📄 text_extractor.py <br> PDF OCR engine]
    Services --> S3[📄 ultrasound_model.py <br> CNN preprocessing]
```

---

## 🧠 Fireworks, AI Models & AMD ROCm Optimization 
## 🔥 Fireworks AI Integration

The platform uses **Fireworks AI**, a serverless LLM inference platform, to turn raw biomarker data and ultrasound predictions into patient-friendly clinical insights.

**Model:** `accounts/fireworks/models/gpt-oss-120b` — chosen for its low cost ($0.15/M input, $0.60/M output), function-calling support, and strong structured-JSON reliability, without the overhead of a larger frontier model.

**How it works:**
- All clinical scores (APRI, FIB-4, BMI) are calculated deterministically in Python — the LLM never invents numbers, it only interprets them.
- `prompt_builder.py` assembles the patient profile, full report history, and CNN ultrasound result into a structured prompt with an embedded scoring rubric.
- The model is instructed to return **only raw JSON**, parsed and validated in `llm.py` before reaching the frontend.
- A low temperature (`0.3`) keeps scores consistent across repeated runs on the same data.

```python
payload = {
    "model": "accounts/fireworks/models/gpt-oss-120b",
    "max_tokens": 1500,
    "temperature": 0.3,
    "messages": [
        {"role": "system", "content": "You are a medical analysis assistant. Provide responses in valid JSON format only."},
        {"role": "user", "content": prompt}
    ]
}
```
### 📷 Deep Learning Ultrasound Model
The platform integrates an image-based computer vision classifier built on **TensorFlow/Keras** utilizing a fine-tuned **MobileNetV2** backbone:
*   **Accuracy**: The model achieved a **97% accuracy** rating on validation datasets for classifying liver scans.
*   **Classification Targets**:
    1.  `HCC` (Hepatocellular Carcinoma) - Malignant liver cancer.
    2.  `Hemangioma` - Benign vascular liver tumor.
    3.  `Normal` - Healthy liver tissue.
*   **Data Pipeline**: OpenCV center-crops raw scans into a square (to prevent image stretching) and resizes them to $224 \times 224 \times 3$, matching the exact normalization pipeline used during model training.

### ⚡ AMD ROCm Acceleration (Hardware Acceleration)
If deploying the Flask API on servers powered by **AMD Instinct™ (e.g. MI210 / MI250 / MI300)** or running locally on **AMD Radeon™ GPUs**:
1.  **Containerize with ROCm**: Run the Flask server inside the official AMD ROCm TensorFlow Docker container:
    ```bash
    docker run -it --network=host --device=/dev/kfd --device=/dev/dri \
      --group-add video --ipc=host --shm-size 8G \
      rocm/tensorflow:latest-release
    ```
2.  **Performance Wins**: Running MobileNetV2 inferences within the ROCm backend container utilizes AMD's hardware matrix engines. Image pre-processing and model execution speeds drop to single-digit milliseconds, allowing real-time multi-frame scan analysis in the field.

---

## 🔌 API Route Specifications

To make the routing system clear, the endpoints are grouped by functional module and detailed below.

### 🔑 1. Authentication & Onboarding (`routes/auth.py`)

Handles user creation, login validations, and updates to the medical/lifestyle profile.

| Method | Endpoint | Description | Expected Payload JSON |
| :--- | :--- | :--- | :--- |
| `POST` | `/auth/signup` | Creates an account, stores an Argon2id password hash, and returns access/refresh tokens. | `{"email":"user@test.com","password":"a long passphrase","confirm_password":"a long passphrase","full_name":"John Doe","terms_accepted":true}` |
| `POST` | `/auth/login` | Validates credentials and returns a new revocable authentication session. | `{"email":"user@test.com","password":"a long passphrase"}` |
| `POST` | `/auth/refresh` | Rotates a refresh token and returns a replacement access/refresh pair. | `{"refresh_token":"..."}` |
| `POST` | `/auth/logout` | Revokes the current session. Requires an access token. | `{}` |
| `GET` | `/auth/me` | Restores the currently authenticated user. | None |
| `POST` | `/onboarding` | Updates the authenticated user's medical background and lifestyle profile. | `{"age":34,"gender":"male","weight":70,"height":175,"diabetes_status":false,"hypertension":false,"previous_liver_disease":false,"family_history":false,"activity_level":"moderately active","exercise_frequency":"2-4 times per week","alcohol_consumption":"occasional","smoking_status":"never"}` |

`/signup` and `/login` remain temporary aliases for the new `/auth/*` routes.
Every endpoint other than signup, login, refresh, and the root health check
requires:

```http
Authorization: Bearer <access_token>
```

User identity comes only from the verified access token. Protected requests
must not include `user_id`.

Signup and login return this authentication shape:

```json
{
  "success": true,
  "user": {
    "user_id": 7,
    "full_name": "John Doe",
    "email": "user@test.com",
    "age": null,
    "gender": null
  },
  "auth": {
    "access_token": "...",
    "refresh_token": "...",
    "token_type": "Bearer",
    "expires_in": 900,
    "access_expires_at": "2026-07-27T12:15:00+00:00",
    "refresh_expires_at": "2026-08-26T12:00:00+00:00"
  }
}
```

The access token lasts 15 minutes. On a protected request returning `401`, the
client should call `/auth/refresh` once, atomically replace both returned
tokens, then retry the original request once. Refresh tokens are one-time-use:
reusing an older token invalidates the user's active sessions. The client must
clear both tokens after refresh failure or logout.

### 📂 2. File Uploads & Processing (`routes/upload.py`)

Accepts physical files and performs automated PDF OCR parsing or convolutional neural network prediction.

| Method | Endpoint | Content Type | Parameters (Form Data) | Internal Logic |
| :--- | :--- | :--- | :--- | :--- |
| `POST` | `/upload` | `multipart/form-data` | `file`: (PDF/Image stream)<br>`report_type`: (`lft`/`cbc`/`coagulation`/`afp`/`hepatitis`/`ultrasound`) | **If ultrasound**: crops image, runs MobileNetV2, predicts condition.<br>**If lab report**: runs Tesseract/PyMuPDF text extraction and extracts values using regex. |
| `GET` | `/recent-reports` | None | None | Returns only the authenticated user's recent uploads. |

Lab reports must be valid PDF files. Ultrasounds must be valid JPEG or PNG
images. Uploads are limited by `MAX_UPLOAD_BYTES`, saved under random temporary
names, and deleted immediately after extraction or prediction.

### 📊 3. Clinical Indices & Generative AI (`routes/calculate.py`, `insights.py`, `report_analysis.py`)

Forces metric calculations or queries the Fireworks AI LLM to interpret liver panels.

| Method | Endpoint | Route Blueprint | Description | Expected Payload JSON |
| :--- | :--- | :--- | :--- | :--- |
| `POST` | `/calculate` | `calculate.py` | Recalculates and saves latest APRI & FIB-4 scores from blood panel results. | `{"age":34}` |
| `POST` | `/insights` | `insights.py` | Requests generalized fitness and lifestyle suggestions based on authenticated history. | `{}` |
| `POST` | `/report-analysis` | `report_analysis.py` | Returns deterministic health/risk values and cached AI explanations for one saved report. | `{"report_id":42}` |

### 4. Dashboard (`routes/dashboard.py`)

Returns the dashboard-ready health score, latest biomarker values and trends,
structured AI insights, and the next suggested test.

| Method | Endpoint |
| :--- | :--- |
| `GET` | `/dashboard` |

Example:

```http
GET /dashboard
Authorization: Bearer <access_token>
```

The response always contains every supported biomarker. When a biomarker has not
been extracted, its `score`, `status`, and `trend` are all `null`. Biomarker
trends compare the latest non-empty value with the previous non-empty value.
The health-score trend compares the latest two saved reports. The response also
contains exactly three AI insight objects and the next two suggested tests.
Unchanged trends are returned as an empty string. Insight statuses are `normal`,
`monitor`, or `info`.

### 5. AI Report Analysis

Call `POST /report-analysis` after `/calculate` saves the current upload set.
The endpoint returns the health score and trend, a numeric slider-ready risk
level, every supported biomarker with its current value/status/trend/insight,
and an AI summary. Biomarker values always come from the selected current
report; the preceding report is used only for trends.

The AI narrative is cached by `report_id` and analysis version in
`report_analyses`, so opening the same analysis repeatedly does not call the AI
provider again. Deterministic scores, risk, statuses, and trends are recomputed
on each request so they cannot become stale. Missing biomarker values and their
status, trend, and insight are returned as `null`.

### 6. Health Insights

Call `POST /health-insights` with the optional `report_id` used for report
analysis:

```json
{
  "report_id": 42
}
```

The response provides a short health-score summary, four current-status cards,
all biomarker clinical insights, four positive-change cards, paired risk
factors, four monitoring areas, and a recommendation. It reuses the shared
biomarker calculations and cached report narrative instead of making a second
AI request.

### 7. Health Assistant Chat

Call `POST /assistant/chat` to start or continue a patient conversation. The
first request may include a `report_id`; when omitted, the latest saved report
is used. The chosen report remains fixed for that conversation so later uploads
cannot silently change the clinical context.

Start a conversation:

```json
{
  "report_id": 42,
  "message": "Is my ALT improving?"
}
```

Continue it using the returned `conversation_id`:

```json
{
  "conversation_id": "fae67f3f-bb16-4bc1-98cf-654d6018af24",
  "message": "What should I ask my doctor?"
}
```

The response includes `reply`, `context_report_id`, and
`requires_urgent_care`. Conversations and messages are stored in PostgreSQL,
while only the most recent 12 messages are sent to the model. The model receives
a minimized profile and only the selected report, not the user's email or full
report history.

The conversation and selected report must belong to the authenticated user.

---

## ⚙️ System Prerequisites

Your host system must run the following dependencies to operate OCR and file loading correctly:
1.  **Python 3.10+**
2.  **Tesseract OCR Engine**:
    *   *Windows*: Install the binaries (e.g. from UB Mannheim) and set the directory path in your system variables or specify the path to `tesseract.exe` in `services/text_extractor.py`.
    *   *Linux (Ubuntu/Debian)*: `sudo apt-get install tesseract-ocr libtesseract-dev`
    *   *macOS*: `brew install tesseract`
3.  **poppler-utils** (Needed by `pdf2image` to preprocess PDF pages into images for OCR processing):
    *   *Windows*: Download poppler-utils and add the `/bin` directory to your system environment variables.
    *   *Linux (Ubuntu/Debian)*: `sudo apt-get install poppler-utils`
    *   *macOS*: `brew install poppler`

---

## 🚀 Installation & Local Execution

1.  **Clone the Repository**:
    ```bash
    git clone https://github.com/namanmalik385/Livora-Ai.git
    cd Livora-Ai
    ```
2.  **Set Up Virtual Environment**:
    ```bash
    python -m venv venv
    # Windows Activation:
    .\venv\Scripts\activate
    # macOS/Linux Activation:
    source venv/bin/activate
    ```
3.  **Install Libraries**:
    ```bash
    pip install -r requirements.txt
    ```
4.  **Create `.env` Configuration File**:
    Copy `.env.example` to `.env`. Generate `JWT_SECRET` with
    `python -c "import secrets; print(secrets.token_urlsafe(48))"` and set the
    remaining values:
    ```env
    DATABASE_URL=postgresql://neondb_owner:PASSWORD@HOST/neondb?sslmode=require
    JWT_SECRET=
    JWT_ISSUER=livora-api
    JWT_AUDIENCE=livora-mobile
    CORS_ORIGINS=http://localhost:8081,http://localhost:19006
    APP_ENV=development
    ENFORCE_HTTPS=0
    FIREWORKS_API_KEY=your_fireworks_api_key
    GROQ_API_KEY=your_groq_api_key
    GROQ_MODEL=llama-3.3-70b-versatile
    ```
5.  **Start the Flask App**:
    ```bash
    python app.py
    ```
    This initializes the PostgreSQL user, authentication-session, rate-limit,
    report, upload-history, analysis, and assistant tables, then launches the
    Flask server at `http://127.0.0.1:5000`.

---

## 📈 Clinical Indices & Math

### FIB-4 Index (Fibrosis-4 Index)
Estimates liver fibrosis severity by incorporating age and enzymes:
$$\text{FIB-4} = \frac{\text{Age (years)} \times \text{AST (U/L)}}{\text{Platelets } (10^9/\text{L}) \times \sqrt{\text{ALT (U/L)}}}$$

### APRI Score (AST to Platelet Ratio Index)
Evaluates cirrhosis risk:
$$\text{APRI} = \frac{\left( \frac{\text{AST Level (U/L)}}{\text{AST Upper Limit of Normal (U/L)}} \right)}{\text{Platelet Count } (10^9/\text{L})} \times 100$$
*(Default upper limit of normal for AST is set to $40 \text{ U/L}$).*

---

## 🗄️ Database Table Schema

### 1. `users` Table
Stores demographics, medical history flags, and baseline lifestyle configurations.

| Column Name | Data Type | Constraints / Defaults |
| :--- | :--- | :--- |
| `id` | SERIAL | PRIMARY KEY |
| `email` | TEXT | UNIQUE, NOT NULL |
| `password_hash` | TEXT | Argon2id hash, NOT NULL |
| `name` | TEXT | |
| `age` | INTEGER | |
| `gender` | TEXT | |
| `weight` | REAL | (kg) |
| `height` | REAL | (cm) |
| `bmi` | REAL | ($\text{weight} / \text{height(m)}^2$) |
| `diabetes_status` | INTEGER | 0 = No, 1 = Yes |
| `hypertension` | INTEGER | 0 = No, 1 = Yes |
| `previous_liver_disease` | INTEGER | 0 = No, 1 = Yes |
| `family_history` | INTEGER | 0 = No, 1 = Yes |
| `activity_level` | TEXT | "sedentary" / "lightly active" / ... |
| `exercise_frequency` | TEXT | "never" / "1-2 times per week" / ... |
| `alcohol_consumption` | TEXT | "none" / "occasional" / ... |
| `smoking_status` | TEXT | "never" / "former" / "current" |
| `terms_accepted_at` | TIMESTAMPTZ | |
| `created_at` | TIMESTAMPTZ | NOT NULL |
| `updated_at` | TIMESTAMPTZ | NOT NULL |

### 2. `auth_sessions` Table
Stores revocable authentication sessions. Refresh tokens are never stored in
plaintext.

| Column Name | Data Type | Constraints / Defaults |
| :--- | :--- | :--- |
| `id` | TEXT | PRIMARY KEY |
| `user_id` | INTEGER | REFERENCES users(id), NOT NULL |
| `refresh_token_hash` | TEXT | SHA-256 hash, NOT NULL |
| `created_at` | TIMESTAMPTZ | NOT NULL |
| `expires_at` | TIMESTAMPTZ | NOT NULL |
| `last_used_at` | TIMESTAMPTZ | |
| `revoked_at` | TIMESTAMPTZ | |

### 3. `auth_rate_limits` Table
Stores server-side counters used to throttle signup, login, and refresh
attempts. The keys are one-way hashes of the rate-limit scope.

| Column Name | Data Type | Constraints / Defaults |
| :--- | :--- | :--- |
| `rate_key` | TEXT | PRIMARY KEY |
| `window_started_at` | TIMESTAMPTZ | NOT NULL |
| `attempts` | INTEGER | NOT NULL |
| `blocked_until` | TIMESTAMPTZ | |

### 4. `reports` Table
Stores chronological values extracted from PDFs and ultrasound predictions.

| Column Name | Data Type | Constraints / Defaults |
| :--- | :--- | :--- |
| `id` | SERIAL | PRIMARY KEY |
| `user_id` | INTEGER | REFERENCES users(id), NOT NULL |
| `age` | INTEGER | Age at time of report |
| `platelets` | REAL | Blood platelet count ($10^9/\text{L}$) |
| `ast` | REAL | Aspartate Aminotransferase (U/L) |
| `alt` | REAL | Alanine Aminotransferase (U/L) |
| `bilirubin` | REAL | Total Bilirubin (mg/dL) |
| `albumin` | REAL | Albumin (g/dL) |
| `inr` | REAL | International Normalized Ratio (Coagulation) |
| `pt` | REAL | Prothrombin Time (seconds) |
| `afp` | REAL | Alpha-Fetoprotein (ng/mL) |
| `hbsag` | INTEGER | Hepatitis B Surface Antigen (0 or 1) |
| `anti_hcv` | INTEGER | Hepatitis C Antibodies (0 or 1) |
| `ast_uln` | REAL | AST Upper Limit of Normal (default 40.0) |
| `apri` | REAL | Calculated APRI Score |
| `fib4` | REAL | Calculated FIB-4 Index |
| `ultrasound_prediction` | TEXT | Prediction outcome: HCC / Hemangioma / Normal |
| `date_added` | TEXT | Formatted creation timestamp, NOT NULL |

### 5. `upload_history` Table
Logs uploaded file actions.

| Column Name | Data Type | Constraints / Defaults |
| :--- | :--- | :--- |
| `id` | SERIAL | PRIMARY KEY |
| `user_id` | INTEGER | REFERENCES users(id), NOT NULL |
| `report_type` | TEXT | e.g. "lft", "cbc", "ultrasound", ... |
| `date_uploaded` | TEXT | Formatted timestamp, NOT NULL |
