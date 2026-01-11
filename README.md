# CuraIQ Health Triage

AI-assisted fever triage application with a Flask backend and a React + Vite frontend.

## Tech Stack

- Frontend: React 18, TypeScript, Vite, Tailwind CSS, shadcn/ui
- Backend: Flask, SQLAlchemy, SQLite

## Prerequisites

- Node.js 18+
- npm 9+
- Python 3.10+

## Backend Setup

```sh
cd backend
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
python app.py
```

The Flask API starts on `http://127.0.0.1:5000` by default, seeds demo data, and exposes routes under `/api/*`.

### Sample Credentials

| Role      | Email                  | Password     |
|-----------|------------------------|--------------|
| Doctor    | doctor@hospital.com    | password123  |
| Clinician | clinician@example.com  | password123  |
| Chemist   | chemist@example.com    | password123  |

## Frontend Setup

```sh
npm install
npm run dev
```

The development server runs on `http://127.0.0.1:5173` and communicates with the Flask API. To target a different backend URL, create `.env` in the repo root and set:

```
VITE_API_BASE_URL=http://localhost:5000
```

## Running the App

1. Start the Flask backend (`python backend/app.py`)
2. Start the React frontend (`npm run dev`)
3. Visit the frontend URL and interact with the diagnosis flow and role-based dashboards

## API Overview

- `POST /api/auth/login` – email/password login per role
- `GET /api/diagnoses`, `POST /api/diagnoses`, `PATCH /api/diagnoses/<id>`
- `GET /api/messages/<id>`, `POST /api/messages`
- `GET /api/prescriptions`, `PATCH /api/prescriptions/<id>`
- `GET /api/inventory`, `POST /api/inventory`
- `GET /api/analytics/summary`

All write operations that change state require an auth token returned from `POST /api/auth/login`.

## Linting and Formatting

```sh
npm run lint
```

The backend follows standard PEP 8 formatting; consider adding `ruff` or `black` to the toolchain if you need automated checks.

