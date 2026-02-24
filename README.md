# AICarServiceAgent# AI Car Service Agent 🚗

Operational backend system for garage booking automation.

## Features

- WhatsApp booking via Twilio
- Slot conflict detection
- Multi-bay slot capacity engine
- Reschedule & cancellation engine
- STRICT booking status transitions
- Reminder scheduler (APScheduler)
- Twilio delivery tracking
- JobCard lifecycle
- Auto-complete booking on JobCard completion
- Reports API

## Tech Stack

- FastAPI
- SQLAlchemy
- SQLite
- Twilio WhatsApp Sandbox
- APScheduler

## Run Locally

```bash
uvicorn main:app --reload