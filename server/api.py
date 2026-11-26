import sqlite3
from datetime import date as Date
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from database import check_doctor_availability, init_db

DB_PATH = Path(__file__).parent / "caredesk.db"

# Keep these names in sync with SYSTEM_PROMPT in bot.py
DOCTORS = [
    {"name": "Dr. Priya Sharma", "speciality": "General Physician"},
    {"name": "Dr. Rahul Mehta", "speciality": "Cardiologist"},
    {"name": "Dr. Anita Reddy", "speciality": "Dermatologist"},
    {"name": "Dr. Vikram Nair", "speciality": "Orthopedist"},
]

app = FastAPI(title="CareDesk API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite default
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    init_db()


@app.get("/api/doctors")
def list_doctors():
    return DOCTORS


@app.get("/api/doctors/{name}/slots")
def doctor_slots(name: str, date: str | None = Query(default=None)):
    if date is None:
        date = Date.today().isoformat()
    # Reuse the same function the voice agent calls, so both show identical data
    return check_doctor_availability(doctor_name=name, date=date)


@app.get("/api/appointments")
def list_appointments():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT * FROM appointments ORDER BY date, time"
        ).fetchall()
    finally:
        conn.close()
    return [dict(row) for row in rows]