const API = "http://localhost:8000";

export function todayISO() {
  const d = new Date();
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 10);
}

export async function getDoctors() {
  const res = await fetch(`${API}/api/doctors`);
  return res.json();
}

export async function getSlots(doctorName, date) {
  const res = await fetch(
    `${API}/api/doctors/${encodeURIComponent(doctorName)}/slots?date=${date}`
  );
  return res.json();
}

export async function getAppointments() {
  const res = await fetch(`${API}/api/appointments`);
  return res.json();
}