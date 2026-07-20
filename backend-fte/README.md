# Digital FTE Backend

This backend is the authentication service for the Digital FTE project. It provides user signup, local login, Google login, and basic account tracking using FastAPI, async SQLAlchemy, PostgreSQL, and Docker.

## What this backend does

The backend currently focuses on user authentication and account management:

- Create a new local user account
- Log in with email and password
- Log in with a Google ID token
- Store login activity records such as login method, IP address, and user-agent
- Expose a simple health check endpoint

It is designed to support the frontend by providing a clean API for authentication flows.

## Tech stack

- FastAPI for the API layer
- Async SQLAlchemy for database access
- PostgreSQL as the main database
- Alembic for database migrations
- Redis for future session/token enhancements
- Pydantic for request and response validation
- Passlib with bcrypt for password hashing
- Google OAuth verification using Google Auth libraries
- Docker Compose for local development

## Project structure

```text
backend-fte/
├── app/
│   ├── auth/
│   │   ├── google_oauth.py
│   │   ├── routes.py
│   │   └── service.py
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── dependencies.py
│   ├── models.py
│   ├── schemas.py
│   └── security.py
├── alembic/
├── alembic.ini
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── jwt.py
└── README.md
```

### Key files

- app/main.py: creates the FastAPI app and registers routes
- app/config.py: loads environment variables from .env
- app/database.py: configures the async database engine and session factory
- app/models.py: defines the database tables
- app/schemas.py: defines request and response models
- app/auth/routes.py: exposes authentication endpoints
- app/auth/service.py: contains the business logic for signup/login/google auth
- app/dependencies.py: provides a protected-user dependency for future secured routes

## Prerequisites

Before running the backend, make sure you have:

- Python 3.12 or newer
- Docker Desktop (recommended for PostgreSQL and Redis)
- A terminal with access to pip and venv

## Environment setup

Create a file named .env in the backend root and add the following values:

```env
APP_NAME=Digital FTE Auth Service
ENV=development
DEBUG=True
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/digital_fte
GOOGLE_CLIENT_ID=your_google_client_id
REDIS_URL=redis://localhost:6379/0
```

### Notes

- DATABASE_URL should point to your PostgreSQL instance.
- GOOGLE_CLIENT_ID should be the client ID from your Google OAuth app.
- If you use Docker Compose, the default database host is localhost because the container ports are exposed on your machine.

## Installation

From the backend-fte folder, run:

```bash
python -m venv venv
source venv/bin/activate
# On Windows use: venv\Scripts\activate
pip install -r requirements.txt
```

## Running the database with Docker

If you want to use the included Docker setup, start PostgreSQL and Redis:

```bash
docker compose up -d db redis
```

This will start:

- PostgreSQL on port 5432
- Redis on port 6379

## Running database migrations

The project already contains Alembic migration files. To apply them:

```bash
alembic upgrade head
```

If you change the database models later, create a new migration like this:

```bash
alembic revision --autogenerate -m "describe your change"
alembic upgrade head
```

## Starting the backend

Run the API locally with:

```bash
uvicorn app.main:app --reload
```

The API will be available at:

- http://localhost:8000
- Swagger docs: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## API endpoints

### Health check

- GET /health
- Returns a simple status response to confirm the server is running

### Authentication

- POST /auth/signup
  - Creates a new user account
  - Validates username, email, and password strength
  - Stores the user in the database

- POST /auth/login
  - Authenticates using email and password
  - Returns the authenticated user details

- POST /auth/google
  - Accepts a Google ID token
  - Verifies the token and creates or finds the matching user

## Authentication flow

### 1. Local signup

A user sends a signup request with:

- username
- email
- password
- full_name (optional)

The backend hashes the password with bcrypt and saves the user.

### 2. Local login

A user sends their email and password. The backend:

- checks whether the email exists
- verifies the password
- rejects disabled accounts
- returns the authenticated user

### 3. Google login

A frontend sends a Google ID token to /auth/google. The backend:

- verifies the token with Google
- uses the Google user identity to create or find the account
- stores a login record for auditing

## Database model overview

The backend uses two main tables:

### registered_students

Stores user account information such as:

- username
- email
- full_name
- hashed_password
- auth_provider
- google_id
- is_active
- is_verified

### login_users

Stores login history information such as:

- student_id
- login_method
- ip_address
- user_agent
- logged_in_at

## Protected route support

The project includes a protected-user dependency in app/dependencies.py. This is meant to be used by routes that require a logged-in user, such as profile or account pages.

## Running with Docker

You can also run the full backend stack in containers:

```bash
docker compose up --build
```

This launches:

- the FastAPI app
- PostgreSQL
- Redis

## Common issues

### Module not found errors

If Python complains about missing packages, reinstall dependencies:

```bash
pip install -r requirements.txt
```

### Database connection errors

Check that:

- PostgreSQL is running
- DATABASE_URL is correct
- the database name exists

### Google login errors

Make sure:

- the Google client ID is correct
- the frontend sends a valid Google ID token
- the token was generated from the same Google project

## Next steps

Possible improvements for this backend include:

- adding refresh tokens
- implementing logout and token revocation
- adding stricter rate limiting for login endpoints
- adding profile and account management endpoints
- adding email verification and password reset flows
