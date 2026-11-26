# CareDesk AI: Voice Doctor Appointment Assistant

A voice agent that checks doctor availability, books appointments, and cancels them. Callers identify themselves only by the phone number they say out loud. A React dashboard starts calls in the browser and shows doctors, slots, and appointments.

## LLM
Google Gemini (`gemini-3.5-flash-lite`) via Pipecat's Google Interactions service, with function calling.

## Stack
- Pipecat (Python) voice pipeline with SmallWebRTC transport
- ElevenLabs realtime STT and TTS
- Silero VAD for turn detection
- SQLite for mock doctors, slots, and appointments
- FastAPI for the dashboard API, React + Vite for the dashboard

## Setup

### 1. Environment
Copy `server/.env.example` to `server/.env` and add your keys.

### 2. Voice bot (port 7860)
    cd server
    uv sync
    uv run bot.py

### 3. Dashboard API (port 8000)
    cd server
    uv run uvicorn api:app --port 8000 --reload

### 4. Dashboard (port 5173)
    cd web
    npm install
    npm run dev

Open http://localhost:5173, click **Try Call**, and allow the microphone.

## Tools
- `check_doctor_availability(doctor_name, date)`
- `book_appointment(doctor_name, date, time, patient_phone)`
- `cancel_appointment(patient_phone, doctor_name)`
