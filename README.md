# Chain of Custody Evidence System

A secure Python backend for managing chain-of-custody evidence with encrypted file storage, two-party transfer handshakes, and immutable audit logs.

## Features

- **Secure Authentication**: JWT tokens with Argon2id password hashing
- **Role-based Access**: ADMIN, COLLECTOR, ANALYST, AUDITOR roles
- **Encrypted File Storage**: AES-256-GCM encryption at rest
- **Chain of Custody**: Two-party transfer handshake system
- **Immutable Audit Log**: Hash-chained audit entries for tamper detection
- **File Integrity**: SHA-256 verification for all files

## Tech Stack

- Python 3.11
- FastAPI + Uvicorn
- SQLAlchemy 2.x + SQLite
- Pydantic v2
- Cryptography (AES-256-GCM)
- JWT authentication

## Setup

### 1. Create Virtual Environment

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# Linux/Mac
python -m venv .venv
source .venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Generate AES Key

```bash
python -c "import os,base64; print(base64.b64encode(os.urandom(32)).decode())"
```

### 4. Configure Environment

```bash
# Copy example config
cp .env.example .env

# Edit .env with your values:
# - Set SECRET_KEY to a long random string
# - Set APP_AES_KEY_BASE64 to the generated key from step 3
```

### 5. Create Admin User

```bash
python create_admin.py
```

### 6. Run Server

```bash
uvicorn backend.app:app --reload
```

The API will be available at `http://localhost:8000`

## API Documentation

Once running, visit:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## API Examples

### 1. Login

```bash
curl -X POST "http://localhost:8000/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@example.com",
    "password": "your_password"
  }'
```

### 2. Create Evidence with Files

```bash
curl -X POST "http://localhost:8000/evidence/" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -F "agency=FBI" \
  -F "case_no=2024-001" \
  -F "offense=Fraud" \
  -F "item_no=001" \
  -F "badge_no=12345" \
  -F "location=123 Main St" \
  -F "collected_at=2024-01-15T10:30:00Z" \
  -F "description=Laptop computer seized from suspect" \
  -F "files=@evidence1.pdf" \
  -F "files=@photo1.jpg"
```

### 3. Request Transfer

```bash
curl -X POST "http://localhost:8000/transfer/request" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "evidence_id": 1,
    "to_user_id": 2,
    "reason": "Transfer to lab for analysis"
  }'
```

### 4. Accept Transfer

```bash
curl -X POST "http://localhost:8000/transfer/accept/1" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

### 5. Download File (Current Custodian Only)

```bash
curl -X GET "http://localhost:8000/evidence/1/download/1" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  --output downloaded_file.pdf
```

### 6. View Audit Log

```bash
curl -X GET "http://localhost:8000/audit/1" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

## User Roles

- **ADMIN**: Can register users, view all evidence
- **COLLECTOR**: Can create evidence, view own evidence
- **ANALYST**: Can create evidence, view own evidence
- **AUDITOR**: Can view all evidence and audit logs (read-only)

## Security Features

### File Encryption
- Files encrypted with AES-256-GCM
- Unique nonce per file
- Master key stored in environment variable
- Files stored as: `nonce(12) + ciphertext + tag(16)`

### Audit Chain
- Each audit entry contains hash of previous entry
- Tamper detection through hash verification
- Immutable log of all evidence operations

### Access Control
- JWT tokens with role-based permissions
- Only current custodian can download files
- Two-party handshake for transfers

## Project Structure

```
backend/
├── app.py              # FastAPI application
├── db.py               # Database configuration
├── core/
│   ├── config.py       # Settings and configuration
│   ├── security.py     # Authentication helpers
│   ├── crypto.py       # File encryption/decryption
│   └── audit.py        # Audit hash chain helpers
├── models/             # SQLAlchemy models
│   ├── user.py
│   ├── evidence.py
│   ├── transfer.py
│   └── audit.py
├── schemas/            # Pydantic schemas
│   ├── auth.py
│   ├── evidence.py
│   └── transfer.py
├── api/                # API endpoints
│   ├── auth.py
│   ├── evidence.py
│   ├── transfer.py
│   └── audit.py
└── storage/            # Encrypted files (gitignored)
```

## Development

### Testing Crypto Functions

```python
from backend.core.crypto import encrypt_file_data, decrypt_file_data

# Test encryption/decryption
test_data = b"Hello, World!"
cipher_path, sha256_hex = encrypt_file_data(test_data)
decrypted = decrypt_file_data(cipher_path)
assert decrypted == test_data
```

### Testing Audit Chain

```python
from backend.core.audit import create_audit_entry, compute_entry_hash

# Test hash chain
entry1 = create_audit_entry(1, 1, "TEST", {"msg": "first"})
entry2 = create_audit_entry(1, 1, "TEST", {"msg": "second"}, entry1["entry_hash_hex"])
```

## Deployment Notes

- Change `SECRET_KEY` and `APP_AES_KEY_BASE64` in production
- Use PostgreSQL instead of SQLite for production
- Set up proper HTTPS/TLS
- Configure proper CORS origins
- Set up log rotation and monitoring

## License

MIT License

## Frontend (Streamlit)

This project includes a minimal Streamlit UI that talks to the FastAPI backend.

### Install frontend dependencies

```bash
pip install streamlit requests streamlit-authenticator streamlit-camera-input-live streamlit-drawable-canvas
```

Optional (only if you want canvas image export):

```bash
pip install pillow numpy
```

### Run the backend

Make sure the API is running first (in another terminal):

```bash
uvicorn backend.app:app --reload
```

### Run the Streamlit app

```bash
streamlit run frontend/app.py
```

The app will open in your browser (usually http://localhost:8501). It communicates with the backend at `http://127.0.0.1:8000`.

### UI Overview

- **Login**: Enter email and password (calls `/auth/login`). Stores JWT in session and uses it for subsequent requests.
- **Dashboard**: Lists your custody evidence (`GET /evidence/`) and your pending transfers (`GET /transfer/pending`). You can view evidence or accept/reject transfers.
- **Create Evidence** (Analyst/Collector/Admin): Fill the form, upload files (or capture via camera/canvas), then submit (`POST /evidence/`).
- **Evidence Detail**: Shows metadata/files, lets the current custodian download files and request transfer, and displays the audit log timeline (`GET /audit/{id}`).
- **Admin Panel** (Admin only): Create users (`POST /auth/register`) and view all evidence.

### Tips

- Evidence list/create endpoints require a trailing slash in the backend: `/evidence/`.
- The UI automatically includes `Authorization: Bearer <token>` for all calls after login.
- 401/403 responses are shown as friendly error messages in the UI.
