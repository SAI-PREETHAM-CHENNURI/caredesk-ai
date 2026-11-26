"""
CareDesk AI - Voice appointment assistant
Pipeline: browser mic → ElevenLabs STT → Gemini → ElevenLabs TTS → browser speaker
Tools: check_doctor_availability, book_appointment, cancel_appointment
"""

import os
import json
from datetime import datetime
from struct import iter_unpack
from time import monotonic

from dotenv import load_dotenv
from loguru import logger

from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.elevenlabs.stt import CommitStrategy, ElevenLabsRealtimeSTTService
from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
from pipecat.services.google.interactions.llm import GoogleInteractionsLLMService
from pipecat.services.llm_service import FunctionCallParams
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.workers.runner import WorkerRunner

from database import (
    init_db,
    check_doctor_availability,
    book_appointment,
    cancel_appointment,
)

load_dotenv(override=True)

SYSTEM_PROMPT = """You are the virtual receptionist for CareDesk Clinic, speaking with a caller on the phone.

Your replies are spoken aloud. Use short, natural sentences. Never use emojis, bullet points, markdown or any formatting that cannot be spoken. Be warm, calm and concise. Ask one question at a time.

You MUST use your tools to answer any question about doctors, availability or appointments. Never answer from memory or make up information.

TOOL USAGE — mandatory:
- When asked about doctors, availability, or slots: call check_doctor_availability immediately.
- When a caller wants to book: call check_doctor_availability first, then book_appointment after phone confirmation.
- When a caller wants to cancel: call cancel_appointment after phone confirmation.

BOOKING RULES:
1. Always ask for the caller's phone number before booking or cancelling. Never call book_appointment or cancel_appointment until you have a phone number from the caller in this conversation.
2. Read the phone number back one digit at a time, separated by spaces, and ask the caller to confirm it before proceeding.
3. Only call book_appointment or cancel_appointment after the caller has confirmed the phone number. Even if the number was given earlier in the call, read it back and get confirmation before cancelling.
4. When checking availability, offer at most three slots to the caller — do not list all of them.
5. If a slot is unavailable, offer alternatives from the check_doctor_availability result.
6. If cancel_appointment returns multiple appointments, ask the caller which one to cancel.
7. Never claim to have booked or cancelled anything unless the tool returned success: true.
8. Use the date format YYYY-MM-DD when calling tools (e.g. 2026-11-26).
9. Use the time format exactly as shown in the slot (e.g. 09:00 AM).
10. When collecting a phone number, wait until the caller has clearly finished. A valid phone number has 10 digits. If the caller gives fewer, ask for the rest before repeating it back.

Available doctors: Dr. Priya Sharma (General Physician), Dr. Rahul Mehta (Cardiologist), Dr. Anita Reddy (Dermatologist), Dr. Vikram Nair (Orthopedist).
"""


def build_system_prompt() -> str:
    today = datetime.now().strftime("%Y-%m-%d (%A)")
    return (
        SYSTEM_PROMPT
        + f"\n\nToday's date is {today}. Convert 'today' and 'tomorrow' "
        "to YYYY-MM-DD using this date. Never guess the date."
    )


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing {name} in server/.env")
    return value


# ── Tool handlers ─────────────────────────────────────────────────────────────

async def handle_check_availability(params: FunctionCallParams):
    args = params.arguments
    logger.info(f"Tool: check_doctor_availability({args})")
    result = check_doctor_availability(
        doctor_name=args.get("doctor_name", ""),
        date=args.get("date"),
    )
    logger.info(f"Result: {result}")
    await params.result_callback(json.dumps(result))


async def handle_book_appointment(params: FunctionCallParams):
    args = params.arguments
    logger.info(f"Tool: book_appointment({args})")
    phone = (args.get("patient_phone") or "").strip()
    if not phone:
        result = {"success": False, "message": "Ask the caller for their phone number first."}
    else:
        result = book_appointment(
            doctor_name=args.get("doctor_name", ""),
            date=args.get("date", ""),
            time=args.get("time", ""),
            patient_phone=phone,
        )
    logger.info(f"Result: {result}")
    await params.result_callback(json.dumps(result))


async def handle_cancel_appointment(params: FunctionCallParams):
    args = params.arguments
    logger.info(f"Tool: cancel_appointment({args})")
    phone = (args.get("patient_phone") or "").strip()
    if not phone:
        result = {"success": False, "message": "Ask the caller for their phone number first."}
    else:
        result = cancel_appointment(
            patient_phone=phone,
            doctor_name=args.get("doctor_name"),
        )
    logger.info(f"Result: {result}")
    await params.result_callback(json.dumps(result))


# ── Tool schemas ──────────────────────────────────────────────────────────────

TOOLS = ToolsSchema(standard_tools=[
    FunctionSchema(
        name="check_doctor_availability",
        description="Check available appointment slots for a doctor, optionally filtered by date.",
        properties={
            "doctor_name": {
                "type": "string",
                "description": "Full or partial name of the doctor, e.g. 'Dr. Sharma' or 'Rahul'.",
            },
            "date": {
                "type": "string",
                "description": "Optional date in YYYY-MM-DD format, e.g. '2026-11-26'.",
            },
        },
        required=["doctor_name"],
    ),
    FunctionSchema(
        name="book_appointment",
        description="Book an appointment slot for a caller. Only call this after the caller has confirmed their phone number.",
        properties={
            "doctor_name": {
                "type": "string",
                "description": "Full or partial name of the doctor.",
            },
            "date": {
                "type": "string",
                "description": "Date in YYYY-MM-DD format.",
            },
            "time": {
                "type": "string",
                "description": "Time exactly as shown in the slot, e.g. '09:00 AM'.",
            },
            "patient_phone": {
                "type": "string",
                "description": "Caller's phone number as spoken and confirmed by the caller.",
            },
        },
        required=["doctor_name", "date", "time", "patient_phone"],
    ),
    FunctionSchema(
        name="cancel_appointment",
        description="Cancel an existing appointment. Only call this after the caller has confirmed their phone number.",
        properties={
            "patient_phone": {
                "type": "string",
                "description": "Caller's phone number as spoken and confirmed by the caller.",
            },
            "doctor_name": {
                "type": "string",
                "description": "Optional: doctor name if the caller specified which appointment to cancel.",
            },
        },
        required=["patient_phone"],
    ),
])


# ── Bot ────────────────────────────────────────────────────────────────────────

class MicMeterSTT(ElevenLabsRealtimeSTTService):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._peak = 0
        self._next_meter_log = monotonic() + 1.0

    async def run_stt(self, audio):
        peak = max((abs(sample) for (sample,) in iter_unpack("<h", audio)), default=0)
        self._peak = max(self._peak, peak)

        now = monotonic()
        if now >= self._next_meter_log:
            logger.info("Mic PCM peak: {}/32768", self._peak)
            self._peak = 0
            self._next_meter_log = now + 1.0

        async for frame in super().run_stt(audio):
            yield frame


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments) -> None:
    logger.info("Starting bot")

    init_db()

    elevenlabs_key = require_env("ELEVENLABS_API_KEY")
    google_key = require_env("GOOGLE_API_KEY")

    stt = MicMeterSTT(
        api_key=elevenlabs_key,
        commit_strategy=CommitStrategy.VAD,
    )

    tts = ElevenLabsTTSService(
        api_key=elevenlabs_key,
        settings=ElevenLabsTTSService.Settings(
            voice=os.getenv("ELEVENLABS_VOICE_ID", "cgSgspJ2msm6clMCkdW9"),
        ),
    )

    llm = GoogleInteractionsLLMService(
        api_key=google_key,
        settings=GoogleInteractionsLLMService.Settings(
            model=os.getenv("GOOGLE_MODEL", "gemini-3.5-flash-lite"),
            system_instruction=build_system_prompt(),
        ),
    )

    # Register tool handlers
    llm.register_function("check_doctor_availability", handle_check_availability)
    llm.register_function("book_appointment", handle_book_appointment)
    llm.register_function("cancel_appointment", handle_cancel_appointment)

    context = LLMContext(tools=TOOLS)
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(
                params=VADParams(
                    confidence=0.4,
                    start_secs=0.2,
                    stop_secs=1.0,  # wait 1s of silence before the bot replies
                    min_volume=0.4,
                ),
            ),
        ),
    )

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            user_aggregator,
            llm,
            tts,
            transport.output(),
            assistant_aggregator,
        ]
    )

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
        observers=[],
    )

    runner = WorkerRunner(handle_sigint=runner_args.handle_sigint)
    await runner.add_workers(worker)

    @worker.rtvi.event_handler("on_client_ready")
    async def on_client_ready(rtvi):
        context.add_message(
            {
                "role": "developer",
                "content": "Greet the caller as the CareDesk Clinic receptionist in one short sentence and ask how you can help.",
            }
        )
        await worker.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info("Client connected")

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Client disconnected")
        await runner.cancel()

    await runner.run()


async def bot(runner_args: RunnerArguments):
    transport_params = {
        "webrtc": lambda: TransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
        ),
    }
    transport = await create_transport(runner_args, transport_params)
    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()