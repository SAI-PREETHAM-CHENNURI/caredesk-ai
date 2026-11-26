export default function AppointmentPanel({ appointments }) {
  return (
    <section>
      <h2>Appointments</h2>
      {appointments.length === 0 ? (
        <p className="muted">No appointments booked.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Doctor</th>
              <th>Date</th>
              <th>Time</th>
              <th>Phone</th>
            </tr>
          </thead>
          <tbody>
            {appointments.map((a) => (
              <tr key={a.id}>
                <td>{a.doctor_name}</td>
                <td>{a.date}</td>
                <td>{a.time}</td>
                <td>{a.patient_phone}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}