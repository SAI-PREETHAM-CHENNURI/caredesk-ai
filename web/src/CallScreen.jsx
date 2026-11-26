import { useEffect, useRef, useState } from "react";
import { PipecatClient } from "@pipecat-ai/client-js";
import { SmallWebRTCTransport } from "@pipecat-ai/small-webrtc-transport";

const BOT_URL = "http://localhost:7860";
const BARS = Array.from({ length: 48 }, (_, i) => {
  // Shape the bars like a voice envelope: taller in the middle
  const x = (i / 47) * Math.PI;
  return 0.25 + 0.75 * Math.sin(x) ** 1.4;
});

function fmt(seconds) {
  const m = String(Math.floor(seconds / 60)).padStart(2, "0");
  const s = String(seconds % 60).padStart(2, "0");
  return `${m}:${s}`;
}

export default function CallScreen({ onClose }) {
  // ringing | connected | ended
  const [state, setState] = useState("ringing");
  const [speaking, setSpeaking] = useState(null); // "assistant" | "user" | null
  const [muted, setMuted] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [lines, setLines] = useState([]);
  const clientRef = useRef(null);
  const audioRef = useRef(null);
  const transcriptRef = useRef(null);

  const addLine = (role, text) => {
    if (!text || !text.trim()) return;
    setLines((prev) => {
      const last = prev[prev.length - 1];
      if (last && last.role === role && last.text === text) return prev;
      return [...prev, { role, text }];
    });
  };

  useEffect(() => {
    const client = new PipecatClient({
      transport: new SmallWebRTCTransport(),
      enableMic: true,
      enableCam: false,
      callbacks: {
        onConnected: () => setState("connected"),
        onDisconnected: () => setState("ended"),
        onTrackStarted: (track, participant) => {
          if (track.kind !== "audio" || participant?.local) return;
          if (!audioRef.current) return;
          audioRef.current.srcObject = new MediaStream([track]);
          audioRef.current.play().catch((e) => console.error("Audio play failed", e));
        },
        onBotStartedSpeaking: () => setSpeaking("assistant"),
        onBotStoppedSpeaking: () => setSpeaking((s) => (s === "assistant" ? null : s)),
        onUserStartedSpeaking: () => setSpeaking("user"),
        onUserStoppedSpeaking: () => setSpeaking((s) => (s === "user" ? null : s)),
        onBotTranscript: (d) => addLine("assistant", d.text),
        onUserTranscript: (d) => {
          if (d.final) addLine("user", d.text);
        },
        onError: (e) => console.error("Pipecat error", e),
      },
    });
    clientRef.current = client;

    client
      .startBotAndConnect({
        endpoint: `${BOT_URL}/start`,
        requestData: {
          createDailyRoom: false,
          enableDefaultIceServers: true,
          transport: "webrtc",
        },
      })
      .catch((e) => {
        console.error("Connect failed", e);
        setState("ended");
      });

    return () => {
      client.disconnect();
    };
  }, []);

  useEffect(() => {
    if (state !== "connected") return;
    const id = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(id);
  }, [state]);

  useEffect(() => {
    transcriptRef.current?.scrollTo({
      top: transcriptRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [lines]);

  function toggleMute() {
    const next = !muted;
    clientRef.current?.enableMic(!next);
    setMuted(next);
  }

  function endCall() {
    clientRef.current?.disconnect();
    setState("ended");
    setTimeout(onClose, 800);
  }

  const latest = lines[lines.length - 1];
  const label = {
    ringing: "Calling…",
    connected: fmt(seconds),
    ended: "Call ended",
  }[state];
  const barColor = speaking === "user" ? "blue" : "green";

  return (
    <div className="phone-backdrop">
      <div className={`phone phone-${state}`}>
        <audio ref={audioRef} autoPlay />

        <div className="badge-live">
          <span className="dot-red" /> LIVE CALL
        </div>
        <h2 className="call-title">
          AI Receptionist <span className="hl">books an appointment</span> LIVE
        </h2>
        <p className="call-sub">{label}</p>

        <div className="party-row">
          <div className={`party ${speaking === "assistant" ? "active green" : ""}`}>
            <div className="avatar green-bg">🤖</div>
            <div>
              <div className="party-label">AI RECEPTIONIST</div>
              <div className="party-name">Dr. Clinic Bot</div>
              <div className="party-status">
                <span className={`pdot ${speaking === "assistant" ? "green" : ""}`} />
                {speaking === "assistant" ? "speaking" : "listening"}
              </div>
            </div>
          </div>
          <div className={`party ${speaking === "user" ? "active blue" : ""}`}>
            <div className="avatar blue-bg">👤</div>
            <div>
              <div className="party-label">ON THE CALL</div>
              <div className="party-name">Patient</div>
              <div className="party-status">
                <span className={`pdot ${speaking === "user" ? "blue" : ""}`} />
                {speaking === "user" ? "speaking" : "listening"}
              </div>
            </div>
          </div>
        </div>

        <div className={`wave-panel ${speaking ? `glow-${barColor}` : ""}`}>
          {BARS.map((h, i) => (
            <span
              key={i}
              className={`bar ${barColor} ${speaking ? "moving" : ""}`}
              style={{
                height: `${Math.round(h * 100)}%`,
                animationDelay: `${(i % 12) * 0.05}s`,
              }}
            />
          ))}
        </div>

        <div className={`caption-card ${latest?.role === "user" ? "blue" : "green"}`}>
          {latest ? (
            <>
              <span className="caption-tag">
                ● {latest.role === "user" ? "PATIENT" : "AI RECEPTIONIST"}
              </span>
              <p className="caption-text">{latest.text}</p>
            </>
          ) : (
            <p className="muted">Live transcript appears here.</p>
          )}
        </div>

        <div className="transcript" ref={transcriptRef}>
          {lines.map((l, i) => (
            <div key={i} className={`msg ${l.role}`}>
              <span className="speaker">
                {l.role === "user" ? "Patient" : "AI receptionist"}
              </span>
              <div className={`bubble ${l.role}`}>{l.text}</div>
            </div>
          ))}
        </div>

        <div className="phone-controls">
          <button
            className={`ctrl ${muted ? "on" : ""}`}
            onClick={toggleMute}
            disabled={state !== "connected"}
          >
            {muted ? "Unmute" : "Mute"}
          </button>
          <button className="ctrl end" onClick={endCall}>
            End call
          </button>
        </div>
      </div>
    </div>
  );
}