# PT Manager — Backend API

A production-ready, multi-tenant REST API for personal trainers to manage clients, training sessions, nutrition, and subscriptions. Built with FastAPI, SQLModel, and PostgreSQL. Deployed on Render via Docker.

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Architecture](#architecture)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Environment Variables](#environment-variables)
  - [Running with Docker Compose](#running-with-docker-compose)
  - [Running Locally](#running-locally)
- [API Reference](#api-reference)
  - [Authentication](#authentication)
  - [Clients](#clients)
  - [Training Sessions](#training-sessions)
  - [Session Packs](#session-packs)
  - [Pack Types](#pack-types)
  - [Nutrition](#nutrition)
  - [Training Plans](#training-plans)
  - [Exercises](#exercises)
  - [Supplements](#supplements)
  - [Assessments](#assessments)
  - [Check-ins](#check-ins)
  - [Billing](#billing)
  - [Notifications](#notifications)
  - [Admin](#admin)
  - [Trainer Profile](#trainer-profile)
  - [Client Portal](#client-portal)
  - [Health Check](#health-check)
- [Database Schema](#database-schema)
- [Authentication & Authorization](#authentication--authorization)
- [Subscription System](#subscription-system)
- [Stripe Integration](#stripe-integration)
- [Background Jobs](#background-jobs)
- [Testing](#testing)
- [Deployment](#deployment)
- [Project Structure](#project-structure)

---

## Overview

PT Manager is a SaaS backend designed for personal trainers. Each trainer operates in their own isolated tenant, managing their clients' training sessions, workout programs, meal plans, supplements, progress assessments, and billing — all through a single unified API.

Clients access their own portal to view their plans, check-in progress data, and upcoming sessions. The platform enforces subscription limits, automatically upgrading tiers as trainer client counts grow.

---

## Features

- **Multi-tenancy** — Trainers are fully isolated; each sees only their own clients and data
- **Role-based access control** — Three roles: `superuser`, `trainer`, `client`
- **JWT authentication with logout support** — Active tokens tracked in the database
- **Stripe subscription billing** — Trial → Paid, with automatic tier management
- **Training session management** — Schedule, complete, cancel, and mark sessions as missed
- **Session pack system** — Clients purchase packs; sessions are consumed on completion
- **Workout program builder** — Multi-day training plans with exercises and set/rep schemes
- **Nutrition module** — Food database, meal plans, and macro calculator
- **Supplement tracking** — Catalog and client-specific supplement assignments
- **Initial assessments & periodic check-ins** — Track client progress over time
- **In-app notifications** — With session reminders via background jobs
- **Email notifications** — Transactional email via Resend
- **Image uploads** — Cloudinary integration for logos and photos
- **Admin dashboard** — Platform-wide metrics, trainer management, billing exemptions
- **Idempotent SQL migrations** — Safe to run on every deploy
- **Soft deletes** — Clients, supplements, and meal plans are archived, not deleted

---

## Tech Stack

| Layer | Technology |
| --- | --- |
| Framework | [FastAPI](https://fastapi.tiangolo.com/) 0.115 |
| ORM | [SQLModel](https://sqlmodel.tiangolo.com/) 0.0.22 (SQLAlchemy + Pydantic) |
| Database | PostgreSQL 16 (SQLite for local dev) |
| Auth | python-jose (JWT) + passlib/bcrypt |
| Payments | Stripe API |
| Email | Resend API |
| Image storage | Cloudinary |
| Background jobs | APScheduler 3.10 |
| ASGI server | Uvicorn |
| Container | Docker + Docker Compose |
| Deployment | Render.com |
| Testing | pytest + httpx + pytest-cov |
| Linting | Ruff |
| Python | 3.12 |

---

## Architecture

```text
┌─────────────────────────────────────────────────────────────────┐
│                          FastAPI App                            │
│                                                                 │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌────────────┐  │
│  │ Routers  │ → │ Services │ → │   CRUD   │ → │  SQLModel  │  │
│  │ /api/v1  │   │ Business │   │  Data    │   │  + Pydantic│  │
│  │          │   │  Logic   │   │  Access  │   │  Schemas   │  │
│  └──────────┘   └──────────┘   └──────────┘   └────────────┘  │
│                                                       │         │
│  ┌──────────────────────────────────────────────────┐│         │
│  │              Database Layer                       ││         │
│  │  PostgreSQL  ─  SQLModel ORM  ─  SQL Migrations  ││         │
│  └──────────────────────────────────────────────────┘│         │
│                                                       ↓         │
│  ┌─────────┐  ┌─────────┐  ┌──────────┐  ┌──────────────────┐ │
│  │ Stripe  │  │  Resend │  │Cloudinary│  │  APScheduler     │ │
│  │Payments │  │  Email  │  │  Images  │  │  Background Jobs │ │
│  └─────────┘  └─────────┘  └──────────┘  └──────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

**Request flow**: HTTP request → CORS middleware → JWT dependency → Router → Service → CRUD → Database

---

## Getting Started

### Prerequisites

- Python 3.12+
- PostgreSQL 16 (or use Docker Compose)
- Docker & Docker Compose (recommended)
- A Stripe account (for billing features)
- A Resend account (for email features)
- A Cloudinary account (for image uploads)

### Environment Variables

Copy `.env.example` to `.env` and fill in the values:

```bash
cp .env.example .env
```

| Variable | Description | Default |
| --- | --- | --- |
| `DATABASE_URL` | PostgreSQL connection string | — |
| `SECRET_KEY` | JWT signing key (keep secret!) | — |
| `API_KEY` | Global API key for middleware auth | — |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | JWT token lifetime | `60` |
| `TRIAL_DAYS` | Free trial period in days | `15` |
| `CORS_ORIGINS` | Comma-separated allowed origins | — |
| `STRIPE_SECRET_KEY` | Stripe API secret key | — |
| `STRIPE_WEBHOOK_SECRET` | Stripe webhook signing secret | — |
| `STRIPE_PRICE_STARTER` | Stripe price ID for Starter tier | — |
| `STRIPE_PRICE_PRO` | Stripe price ID for Pro tier | — |
| `RESEND_API_KEY` | Resend API key for email | — |
| `EMAIL_FROM` | Sender email address | — |
| `CLOUDINARY_CLOUD_NAME` | Cloudinary cloud name | — |
| `CLOUDINARY_API_KEY` | Cloudinary API key | — |
| `CLOUDINARY_API_SECRET` | Cloudinary API secret | — |
| `SUPERUSER_EMAIL` | Seed superuser email | — |
| `SUPERUSER_PASSWORD` | Seed superuser password | — |
| `SUPERUSER_NAME` | Seed superuser display name | — |
| `SEED_DEMO_DATA` | Seed demo trainer/client on startup | `false` |
| `TIMEZONE` | Scheduler timezone | `UTC` |
| `NOTIFICATION_TEST_MODE` | Suppress real email sends | `false` |

### Running with Docker Compose

```bash
# Start PostgreSQL and API together
docker-compose up --build

# API will be available at http://localhost:8000
# Interactive docs at http://localhost:8000/docs
```

### Running Locally

```bash
# Create and activate a virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set up environment
cp .env.example .env
# Edit .env with your values

# Run the application
uvicorn app.main:app --reload --port 8000
```

Database tables are created automatically on startup. Migrations run idempotently on every startup, so no manual migration step is needed.

---

## API Reference

Base URL: `/api/v1`

Interactive documentation is available at `/docs` (Swagger UI) and `/redoc`.

All protected endpoints require a `Bearer` token in the `Authorization` header.

---

### Authentication

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| POST | `/auth/login` | Public | Login and receive JWT |
| POST | `/auth/logout` | JWT | Invalidate current token |
| POST | `/auth/users` | Trainer | Create a user (client account) |
| GET | `/auth/users` | Trainer | List trainer's users |
| GET | `/auth/users/me` | JWT | Get own profile |
| PATCH | `/auth/users/{id}` | JWT | Update user (self or trainer) |
| POST | `/auth/users/me/change-password` | JWT | Change own password |
| POST | `/signup/trainer` | Public | Register a new trainer account |

Login example:

```json
POST /api/v1/auth/login
{
  "email": "trainer@example.com",
  "password": "your_password"
}
```

```json
{
  "access_token": "eyJ...",
  "role": "trainer",
  "user_id": "uuid",
  "full_name": "John Doe"
}
```

---

### Clients

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| GET | `/clients` | Active Sub | List clients (paginated, filterable) |
| POST | `/clients` | Active Sub | Create a new client |
| GET | `/clients/me` | Client | Get own profile with active pack |
| GET | `/clients/{id}` | JWT | Get client details |
| PATCH | `/clients/{id}` | Active Sub | Update client data |
| POST | `/clients/{id}/archive` | Active Sub | Archive (soft-delete) client |
| POST | `/clients/{id}/unarchive` | Active Sub | Reactivate archived client |
| DELETE | `/clients/{id}` | Active Sub | Delete client |

---

### Training Sessions

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| GET | `/sessions` | JWT | List sessions (filter by client_id) |
| POST | `/sessions/clients/{id}` | Active Sub | Schedule a session for a client |
| PUT | `/sessions/{id}` | JWT | Update session details |
| POST | `/sessions/{id}/complete` | JWT | Complete session (consumes pack) |
| POST | `/sessions/{id}/missed` | JWT | Mark session as missed (no-show) |
| POST | `/sessions/{id}/cancel` | JWT | Cancel a session |

Session statuses: `scheduled` → `completed` / `cancelled` / `missed`

---

### Session Packs

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| POST | `/packs/clients/{id}/purchase` | JWT | Purchase a pack for a client |
| GET | `/packs/clients/{id}` | JWT | List all packs for a client |
| GET | `/packs/clients/{id}/active` | JWT | Get the client's current active pack |

A client can only have one active pack at a time. Completing a session automatically decrements the pack's session counter.

---

### Pack Types

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| GET | `/pack-types` | JWT | List available pack templates |
| POST | `/pack-types` | Trainer | Create a pack type |
| PATCH | `/pack-types/{id}` | Trainer | Update a pack type |

Pack types define the number of sessions in a package (e.g., 10-session, 20-session).

---

### Nutrition

#### Foods

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| GET | `/nutrition/foods` | JWT | List food items |
| POST | `/nutrition/foods` | Trainer | Create a food item |
| GET | `/nutrition/foods/{id}` | JWT | Get food details |
| PATCH | `/nutrition/foods/{id}` | Trainer | Update food macros |
| DELETE | `/nutrition/foods/{id}` | Trainer | Deactivate food |

#### Meal Plans

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| POST | `/nutrition/meal-plans` | Trainer | Create a meal plan for a client |
| GET | `/nutrition/meal-plans/client/{id}` | JWT | List client's meal plans |
| GET | `/nutrition/meal-plans/{id}` | JWT | Get meal plan with meals and items |
| PATCH | `/nutrition/meal-plans/{id}` | Trainer | Update meal plan |
| DELETE | `/nutrition/meal-plans/{id}` | Trainer | Archive meal plan |

#### Macro Calculator

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| GET | `/nutrition/activity-factors` | Public | Get activity factor options |
| GET | `/nutrition/plan-types` | Public | Get meal plan type options |
| POST | `/nutrition/calculate-macros` | Trainer | Calculate recommended macros |

The macro calculator uses multiple TMB formulas (Harris-Benedict, Mifflin-St Jeor, etc.) and returns results for each.

---

### Training Plans

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| GET | `/training-plans` | JWT | List training plan templates |
| POST | `/training-plans` | Trainer | Create a training plan |
| PUT | `/training-plans/{id}` | Trainer | Update plan details |
| DELETE | `/training-plans/{id}` | Trainer | Delete plan |
| GET | `/training-plans/{id}/days` | JWT | List training days |
| POST | `/training-plans/{id}/days` | Trainer | Add a training day |
| PUT | `/training-plans/{id}/days/{day_id}` | Trainer | Update training day |
| DELETE | `/training-plans/{id}/days/{day_id}` | Trainer | Delete training day |
| GET | `/training-plans/days/{id}/exercises` | JWT | List exercises in a day |
| POST | `/training-plans/days/{id}/exercises` | Trainer | Add exercise to day |
| PUT | `/training-plans/days/exercises/{id}` | Trainer | Update exercise in day |
| DELETE | `/training-plans/days/exercises/{id}` | Trainer | Remove exercise from day |
| GET | `/training-plans/days/exercises/{id}/loads` | JWT | Get set/rep schemes |
| POST | `/training-plans/days/exercises/{id}/loads` | Trainer | Add set/rep scheme |
| GET | `/training-plans/active-plan/{client_id}` | JWT | Get client's active plan |
| POST | `/training-plans/active-plan` | Trainer | Assign plan to client |
| POST | `/training-plans/clients/{id}/active/close` | Trainer | Close client's active plan |
| POST | `/training-plans/{id}/clone-to-client/{client_id}` | Trainer | Clone plan to a client |

---

### Exercises

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| GET | `/exercises` | JWT | List exercise library |
| POST | `/exercises` | Trainer | Create an exercise |
| PUT | `/exercises/{id}` | Trainer | Update exercise |
| DELETE | `/exercises/{id}` | Trainer | Delete exercise |

---

### Supplements

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| GET | `/supplements` | JWT | List supplement catalog |
| POST | `/supplements` | Trainer | Create a supplement |
| GET | `/supplements/{id}` | JWT | Get supplement details |
| PATCH | `/supplements/{id}` | Trainer | Update supplement |
| POST | `/supplements/{id}/archive` | Trainer | Archive supplement |
| POST | `/supplements/{id}/unarchive` | Trainer | Unarchive supplement |
| DELETE | `/supplements/{id}` | Trainer | Permanently delete |
| GET | `/client-supplements/clients/{id}/supplements` | JWT | List client's supplements |
| POST | `/client-supplements/clients/{id}/supplements` | Trainer | Assign supplement to client |

---

### Assessments

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| POST | `/assessments` | Active Sub | Create initial assessment |
| GET | `/assessments/client/{id}` | JWT | List client's assessments |
| GET | `/assessments/{id}` | JWT | Get assessment details |
| PATCH | `/assessments/{id}` | Trainer | Update assessment |

---

### Check-ins

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| POST | `/checkins` | JWT | Submit a progress check-in |
| GET | `/checkins/client/{id}` | JWT | List client's check-ins |
| GET | `/checkins/{id}` | JWT | Get check-in details |

---

### Billing

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| GET | `/billing/subscription` | Trainer | Get subscription status and limits |
| POST | `/billing/checkout` | Trainer | Create Stripe checkout session |
| POST | `/billing/portal` | Trainer | Open Stripe billing portal |
| POST | `/stripe/webhook` | Stripe Signature | Handle Stripe webhook events |

---

### Notifications

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| GET | `/notifications` | JWT | List notifications |
| PATCH | `/notifications/{id}` | JWT | Mark notification as read/unread |

---

### Admin

> Requires `superuser` role.

| Method | Path | Description |
| --- | --- | --- |
| GET | `/admin/metrics` | Platform-wide metrics (trainers, clients, revenue) |
| GET | `/admin/trainers` | List all trainers with subscription status |
| POST | `/admin/trainers/{id}/suspend` | Deactivate a trainer account |
| POST | `/admin/trainers/{id}/activate` | Reactivate a suspended trainer |
| POST | `/admin/trainers/{id}/grant-exemption` | Grant free PRO access (no billing) |
| POST | `/admin/trainers/{id}/revoke-exemption` | Remove billing exemption |

---

### Trainer Profile

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| GET | `/trainer/profile` | Trainer | Get own trainer profile |
| PATCH | `/trainer/profile` | Trainer | Update profile (name, logo, settings) |

---

### Client Portal

Endpoints for client-facing mobile/web experiences. Clients access their own sessions, plans, check-ins, and progress data.

---

### Health Check

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| GET | `/health` | Public | Returns API and database status |

Used by Render's health check system (every 30 seconds).

---

## Database Schema

The database is managed via idempotent SQL migrations in `app/db/migrations/`. Tables are also created automatically via SQLModel on startup.

### Core Models

| Model | Description |
| --- | --- |
| `User` | Authentication entity with role (`superuser`, `trainer`, `client`) |
| `Client` | Client profile managed by a trainer |
| `TrainerSubscription` | Stripe subscription state per trainer (1:1 with User) |
| `TrainingSession` | A scheduled or completed training session |
| `PackConsumption` | Links completed sessions to a client's pack |
| `PackType` | Template defining the number of sessions in a package |
| `ClientPack` | Purchased instance of a PackType |
| `TrainingPlan` | Workout program template |
| `TrainingPlanDay` | A day within a training plan |
| `Exercise` | Exercise in the library |
| `PlanDayExercise` | Exercise assigned to a training day |
| `PlanExerciseSetLoad` | Set/rep/load scheme for an exercise |
| `Food` | Food item with macros (per 100g) |
| `MealPlan` | Nutritional plan assigned to a client |
| `MealPlanMeal` | A meal within a plan (breakfast, lunch, etc.) |
| `MealPlanItem` | A food item with quantity within a meal |
| `Supplement` | Supplement in the trainer's catalog |
| `ClientSupplement` | Supplement assigned to a client with dosage |
| `InitialAssessment` | Health history and biometric data at intake |
| `Checkin` | Periodic progress check-in by client |
| `Notification` | In-app notification for any user |
| `ActiveToken` | Tracks valid JWT tokens for logout support |
| `TrainerSettings` | Trainer-specific configuration (JSON) |

### Migration History

| File | Changes |
| --- | --- |
| `001_new_modules.sql` | Core schema: users, clients, sessions, packs |
| `002_multitenancy_subscriptions.sql` | Stripe subscription table, multi-tenancy isolation |
| `003_initial_assessment_checkins_modality.sql` | Assessments, check-ins, training modality |
| `004_exempt billing sessions trainer settings.sql` | Billing exemption, session fixes, trainer settings |
| `005_pack_types_multitenancy.sql` | Pack type multi-tenancy |
| `006_active_tokens.sql` | JWT logout support |
| `007_client_supplements.sql` | Client supplement assignments |

---

## Authentication & Authorization

### JWT Flow

1. Client sends credentials to `POST /api/v1/auth/login`
2. Server validates credentials and returns a signed JWT
3. Token is stored in the `active_tokens` table
4. Each request to a protected endpoint validates the JWT signature and checks the database
5. `POST /api/v1/auth/logout` removes the token from the database

### Roles

| Role | Description |
| --- | --- |
| `superuser` | Platform admin. Sees all data, manages trainers |
| `trainer` | Tenant admin. Manages own clients, plans, billing |
| `client` | End user. Reads own data, submits check-ins |

### Subscription-Gated Access

Some trainer endpoints require an **active subscription** (status: `active` or `trialing`). Trainers with expired trials or cancelled subscriptions are blocked from creating or modifying clients.

---

## Subscription System

Trainers start with a 15-day free trial. Tiers scale automatically based on active client count:

| Tier | Clients | Monthly Price |
| --- | --- | --- |
| FREE | 0 – 5 | €0 |
| STARTER | 6 – 49 | €20 |
| PRO | 50+ | €40 |

### Subscription Status Flow

```text
Register
   ↓
TRIALING (15 days free)
   ↓
Trial expires ──────────────────→ TRIAL_EXPIRED (access blocked)
   ↓ (adds payment method)
ACTIVE ──→ payment fails ──→ PAST_DUE (grace period)
                                  ↓ (grace period ends)
                               CANCELLED (access blocked)
```

Superusers can grant a `billing exemption` to any trainer, giving them permanent PRO-tier access without payment.

---

## Stripe Integration

### Trainer Registration Flow

1. `POST /signup/trainer` → creates user, Stripe customer, and trial subscription
2. Trainer uses the app free for 15 days
3. `POST /billing/checkout` → creates Stripe Checkout session to add payment method
4. After successful checkout, Stripe webhook updates the subscription status to `active`

### Webhooks Handled

- `customer.subscription.updated` — Sync subscription status and tier
- `customer.subscription.deleted` — Mark as cancelled
- `invoice.payment_failed` — Mark as past_due

### Automatic Tier Management

When a client is created or archived, `sync_client_count()` recalculates the active client count and updates the Stripe subscription to the correct price tier automatically.

---

## Background Jobs

APScheduler runs background tasks on startup:

- **Session reminders** — Sends notifications (and optionally emails) before scheduled sessions
- **Notification delivery** — Queues and delivers in-app notifications

The scheduler shuts down gracefully on application shutdown.

---

## Testing

```bash
# Run all tests
pytest

# Run with coverage report
pytest --cov=app --cov-report=term-missing

# Run a specific test file
pytest tests/unit/test_macro_calculator.py
```

### Test Structure

```text
tests/
├── auth_tests/
│   └── test_auth.py              # Login, registration, token handling
├── integration/
│   └── test_assessments_router.py # Assessment CRUD integration tests
├── tests_subscription/
│   └── test_subscription.py      # Subscription logic and limits
└── unit/
    └── test_macro_calculator.py   # Nutrition macro calculation
```

---

## Deployment

### Render.com (Production)

The project ships with a `render.yaml` for one-click deployment:

```yaml
# render.yaml
services:
  - type: web
    name: pt-manager-api
    runtime: docker
    healthCheckPath: /api/v1/health
```

1. Connect your GitHub repo to Render
2. Render detects `render.yaml` and builds the Docker image
3. Set all required environment variables in the Render dashboard
4. Render deploys automatically on every push to `main`

### Docker (Self-hosted)

```bash
# Build the image
docker build -t pt-manager-api .

# Run with environment variables
docker run -p 8000:8000 --env-file .env pt-manager-api
```

The application binds to the `PORT` environment variable (defaulting to `8000`), which Render sets automatically.

---

## Project Structure

```text
projeto_back_end/
├── app/
│   ├── main.py                         # App factory, router registration, lifecycle hooks
│   ├── scheduler.py                    # APScheduler setup
│   ├── api/
│   │   ├── deps.py                     # FastAPI dependencies (auth, DB session)
│   │   └── v1/                         # All API routers
│   │       ├── admin.py
│   │       ├── assessments.py
│   │       ├── auth.py
│   │       ├── billing.py
│   │       ├── checkins.py
│   │       ├── client_portal.py
│   │       ├── client_supplements.py
│   │       ├── clients.py
│   │       ├── exercises.py
│   │       ├── health.py
│   │       ├── notifications.py
│   │       ├── nutrition.py
│   │       ├── pack_types.py
│   │       ├── packs.py
│   │       ├── sessions.py
│   │       ├── signup.py
│   │       ├── stripe_webhook.py
│   │       ├── supplements.py
│   │       ├── trainer_profile.py
│   │       └── training_plans.py
│   ├── core/
│   │   ├── config.py                   # Pydantic settings from .env
│   │   ├── security.py                 # JWT, password hashing, RBAC helpers
│   │   ├── logging.py                  # Logging configuration
│   │   └── db_errors.py                # DB error utilities
│   ├── crud/
│   │   ├── assessment.py               # Assessment data access
│   │   └── nutrition.py                # Nutrition data access
│   ├── db/
│   │   ├── session.py                  # Engine and session factory
│   │   ├── base.py                     # SQLModel metadata
│   │   ├── init_db.py                  # Table creation on startup
│   │   ├── migrate.py                  # Migration runner
│   │   ├── migrations/                 # Idempotent SQL migration files
│   │   ├── models/                     # SQLModel ORM models
│   │   └── seeds/                      # Seed data scripts
│   ├── htmls/
│   │   └── email.html                  # Email HTML template
│   ├── schemas/                        # Pydantic request/response schemas
│   ├── services/                       # Business logic layer
│   │   ├── email_service.py
│   │   ├── macro_calculator.py
│   │   ├── notification_service.py
│   │   ├── pack_service.py
│   │   ├── sessions.py
│   │   ├── stripe_service.py
│   │   ├── subscription_service.py
│   │   └── upload_service.py
│   ├── utils/
│   │   └── time.py                     # Timezone-aware datetime helpers
│   └── workers/
│       └── notification_worker.py      # Background notification delivery
├── tests/                              # All tests
├── assets/
│   └── logo.png
├── logs/
│   └── app.log
├── .env.example                        # Environment variable template
├── .dockerignore
├── .gitignore
├── docker-compose.yml                  # Local development environment
├── Dockerfile                          # Production container image
├── render.yaml                         # Render.com deployment config
├── requirements.txt                    # Python dependencies
└── pyproject.toml                      # Project metadata and tooling config
```

---

## License

This project is proprietary software. All rights reserved.
