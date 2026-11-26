import { useEffect, useState } from "react";
import DoctorPanel from "./DoctorPanel";
import AppointmentPanel from "./AppointmentPanel"; 
import CallScreen from "./CallScreen";
import { getDoctors, getAppointments } from "./api";
import "./App.css";

export default function App() {
  const [doctors, setDoctors] = useState([]);
  const [appointments, setAppointments] = useState([]);
  const [callOpen, setCallOpen] = useState(false);

  useEffect(() => {
    getDoctors().then(setDoctors);
  }, []);

  // Refresh appointments every 4 seconds so voice bookings show up live
  useEffect(() => {
    const load = () => getAppointments().then(setAppointments);
    load();
    const id = setInterval(load, 4000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="app">
      <header>
        <h1>CareDesk Clinic</h1>
        <div className="header-right">
          <span className="status">
            <span className="dot" /> Live
          </span>
          <button className="try-call" onClick={() => setCallOpen(true)}>
            Try Call
          </button>
        </div>
      </header>
      <main>
        <DoctorPanel doctors={doctors} />
        <AppointmentPanel appointments={appointments} />
      </main>

      {callOpen && (
        <CallScreen
          onClose={() => {
            setCallOpen(false);
            getAppointments().then(setAppointments);
          }}
        />
      )}
    </div>
  );
}