import { useEffect, useState } from "react";
import { getSlots, todayISO } from "./api";

function toMinutes(time) {
  const [hm, ampm] = time.split(" ");
  let [h, m] = hm.split(":").map(Number);
  if (ampm === "PM" && h !== 12) h += 12;
  if (ampm === "AM" && h === 12) h = 0;
  return h * 60 + m;
}

function DoctorCard({ doctor }) {
  const [slots, setSlots] = useState(null);
  const date = todayISO();

  useEffect(() => {
    getSlots(doctor.name, date).then((data) =>
      setSlots(data.available_slots ?? [])
    );
  }, [doctor.name, date]);

  const sorted = [...(slots ?? [])].sort(
    (a, b) => toMinutes(a.time) - toMinutes(b.time)
  );

  return (
    <div className="card">
      <div className="card-head">
        <div>
          <h3>{doctor.name}</h3>
          <p className="muted">{doctor.specialty}</p>
        </div>
        <span className="count">
          {slots ? `${slots.length} open` : "…"}
        </span>
      </div>
      <div className="slots">
        {sorted.map((s) => (
          <span key={s.slot_id} className="slot">
            {s.time}
          </span>
        ))}
        {slots && slots.length === 0 && (
          <span className="muted">No openings today</span>
        )}
      </div>
    </div>
  );
}

export default function DoctorPanel({ doctors }) {
  return (
    <section>
      <h2>Doctors</h2>
      <div className="grid">
        {doctors.map((d) => (
          <DoctorCard key={d.id} doctor={d} />
        ))}
      </div>
    </section>
  );
}