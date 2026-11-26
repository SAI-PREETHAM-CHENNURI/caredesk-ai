"""
CareDesk AI - Database layer
SQLite with mock doctors, slots and appointments.
"""

import sqlite3
import os
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), "caredesk.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.executescript("""
        CREATE TABLE IF NOT EXISTS doctors (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            specialty TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS slots (
            id INTEGER PRIMARY KEY,
            doctor_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            is_booked INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (doctor_id) REFERENCES doctors(id)
        );

        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY,
            slot_id INTEGER NOT NULL,
            patient_phone TEXT NOT NULL,
            doctor_name TEXT NOT NULL,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (slot_id) REFERENCES slots(id)
        );
    """)

    # Seed doctors only if table is empty
    cur.execute("SELECT COUNT(*) FROM doctors")
    if cur.fetchone()[0] == 0:
        doctors = [
            (1, "Dr. Priya Sharma", "General Physician"),
            (2, "Dr. Rahul Mehta", "Cardiologist"),
            (3, "Dr. Anita Reddy", "Dermatologist"),
            (4, "Dr. Vikram Nair", "Orthopedist"),
        ]
        cur.executemany(
            "INSERT INTO doctors (id, name, specialty) VALUES (?, ?, ?)", doctors
        )

        # Generate slots for the next 3 days, starting today
        times = ["09:00 AM", "10:00 AM", "11:00 AM", "02:00 PM", "03:00 PM", "04:00 PM"]
        slot_id = 1
        for day_offset in range(3):
            date_str = (datetime.now() + timedelta(days=day_offset)).strftime("%Y-%m-%d")
            for doctor_id in range(1, 5):
                for time_str in times:
                    cur.execute(
                        "INSERT INTO slots (id, doctor_id, date, time, is_booked) VALUES (?, ?, ?, ?, 0)",
                        (slot_id, doctor_id, date_str, time_str),
                    )
                    slot_id += 1

    conn.commit()
    conn.close()


# ── Tool functions called by the voice agent ──────────────────────────────────

def check_doctor_availability(doctor_name: str, date: str | None = None) -> dict:
    """Return available slots for a doctor, optionally filtered by date."""
    conn = get_connection()
    cur = conn.cursor()

    # Fuzzy match on doctor name
    cur.execute(
        "SELECT id, name, specialty FROM doctors WHERE LOWER(name) LIKE ?",
        (f"%{doctor_name.lower()}%",),
    )
    doctor = cur.fetchone()

    if not doctor:
        conn.close()
        return {
            "found": False,
            "message": f"No doctor found matching '{doctor_name}'. "
                       "Available doctors: Dr. Priya Sharma (General Physician), "
                       "Dr. Rahul Mehta (Cardiologist), "
                       "Dr. Anita Reddy (Dermatologist), "
                       "Dr. Vikram Nair (Orthopedist).",
        }

    if date:
        cur.execute(
            "SELECT id, date, time FROM slots WHERE doctor_id = ? AND date = ? AND is_booked = 0 ORDER BY time",
            (doctor["id"], date),
        )
    else:
        cur.execute(
            "SELECT id, date, time FROM slots WHERE doctor_id = ? AND is_booked = 0 ORDER BY date, time",
            (doctor["id"],),
        )

    slots = [{"slot_id": row["id"], "date": row["date"], "time": row["time"]} for row in cur.fetchall()]
    conn.close()

    if not slots:
        return {
            "found": True,
            "doctor_name": doctor["name"],
            "specialty": doctor["specialty"],
            "available_slots": [],
            "message": f"{doctor['name']} has no available slots" + (f" on {date}" if date else "") + ".",
        }

    return {
        "found": True,
        "doctor_name": doctor["name"],
        "specialty": doctor["specialty"],
        "available_slots": slots[:6],  # Return max 6 slots to keep response concise
    }


def book_appointment(doctor_name: str, date: str, time: str, patient_phone: str) -> dict:
    """Book a slot for a patient. Phone number must already be confirmed by the agent."""
    conn = get_connection()
    cur = conn.cursor()

    # Find doctor
    cur.execute(
        "SELECT id, name FROM doctors WHERE LOWER(name) LIKE ?",
        (f"%{doctor_name.lower()}%",),
    )
    doctor = cur.fetchone()
    if not doctor:
        conn.close()
        return {"success": False, "message": f"Doctor '{doctor_name}' not found."}

    # Find the specific slot
    cur.execute(
        "SELECT id FROM slots WHERE doctor_id = ? AND date = ? AND time = ? AND is_booked = 0",
        (doctor["id"], date, time),
    )
    slot = cur.fetchone()
    if not slot:
        conn.close()
        return {
            "success": False,
            "message": f"The slot with {doctor['name']} on {date} at {time} is not available. "
                       "Please check availability again.",
        }

    # Check if this phone already has an appointment with this doctor on this date
    cur.execute(
        "SELECT id FROM appointments WHERE patient_phone = ? AND doctor_name LIKE ? AND date = ?",
        (patient_phone, f"%{doctor_name}%", date),
    )
    if cur.fetchone():
        conn.close()
        return {
            "success": False,
            "message": f"This phone number already has an appointment with {doctor['name']} on {date}.",
        }

    # Book it
    cur.execute("UPDATE slots SET is_booked = 1 WHERE id = ?", (slot["id"],))
    cur.execute(
        "INSERT INTO appointments (slot_id, patient_phone, doctor_name, date, time, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (slot["id"], patient_phone, doctor["name"], date, time, datetime.now().isoformat()),
    )
    conn.commit()
    appointment_id = cur.lastrowid
    conn.close()

    return {
        "success": True,
        "appointment_id": appointment_id,
        "doctor_name": doctor["name"],
        "date": date,
        "time": time,
        "patient_phone": patient_phone,
        "message": f"Appointment confirmed with {doctor['name']} on {date} at {time}.",
    }


def cancel_appointment(patient_phone: str, doctor_name: str | None = None) -> dict:
    """Cancel appointment(s) for a patient phone number."""
    conn = get_connection()
    cur = conn.cursor()

    if doctor_name:
        cur.execute(
            "SELECT id, slot_id, doctor_name, date, time FROM appointments "
            "WHERE patient_phone = ? AND LOWER(doctor_name) LIKE ?",
            (patient_phone, f"%{doctor_name.lower()}%"),
        )
    else:
        cur.execute(
            "SELECT id, slot_id, doctor_name, date, time FROM appointments WHERE patient_phone = ?",
            (patient_phone,),
        )

    appointments = cur.fetchall()

    if not appointments:
        conn.close()
        return {
            "success": False,
            "message": f"No appointments found for phone number {patient_phone}"
                       + (f" with {doctor_name}" if doctor_name else "") + ".",
        }

    if len(appointments) > 1 and not doctor_name:
        # Multiple appointments — ask agent to clarify
        appt_list = [
            f"{a['doctor_name']} on {a['date']} at {a['time']}"
            for a in appointments
        ]
        conn.close()
        return {
            "success": False,
            "multiple": True,
            "appointments": appt_list,
            "message": "Multiple appointments found. Please ask the caller which one to cancel: "
                       + "; ".join(appt_list),
        }

    appt = appointments[0]
    cur.execute("DELETE FROM appointments WHERE id = ?", (appt["id"],))
    cur.execute("UPDATE slots SET is_booked = 0 WHERE id = ?", (appt["slot_id"],))
    conn.commit()
    conn.close()

    return {
        "success": True,
        "message": f"Appointment with {appt['doctor_name']} on {appt['date']} at {appt['time']} "
                   f"has been cancelled.",
    }


def get_all_doctors() -> list:
    """Return all doctors with their specialties — used by the dashboard."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name, specialty FROM doctors ORDER BY id")
    doctors = [dict(row) for row in cur.fetchall()]
    conn.close()
    return doctors


def get_available_slots() -> list:
    """Return all unbooked slots — used by the dashboard."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT s.id, d.name as doctor_name, d.specialty, s.date, s.time
        FROM slots s JOIN doctors d ON s.doctor_id = d.id
        WHERE s.is_booked = 0
        ORDER BY s.date, s.time, d.name
    """)
    slots = [dict(row) for row in cur.fetchall()]
    conn.close()
    return slots


def get_all_appointments() -> list:
    """Return all appointments — used by the dashboard."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, doctor_name, date, time, patient_phone, created_at
        FROM appointments
        ORDER BY date, time
    """)
    appointments = [dict(row) for row in cur.fetchall()]
    conn.close()
    return appointments


if __name__ == "__main__":
    init_db()
    print("Database initialised.")
    print(f"Doctors: {len(get_all_doctors())}")
    print(f"Available slots: {len(get_available_slots())}")