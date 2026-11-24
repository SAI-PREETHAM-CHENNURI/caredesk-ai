"""CareDesk AI - Phase 1: voice loop.

Pipeline: browser mic -> ElevenLabs STT -> Gemini -> ElevenLabs TTS -> browser speaker.
Run with: uv run bot.py   then open http://localhost:7860/client
"""

import os

from dotenv import load_dotenv
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
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
from pipecat.services.elevenlabs.stt import ElevenLabsRealtimeSTTService
from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
from pipecat.services.google.interactions.llm import GoogleInteractionsLLMService
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.workers.runner import WorkerRunner

load_dotenv(override=True)

# Phase 1 prompt: conversation only. Appointment tools are added in Phase 3,
# so for now the agent must not claim to have booked or cancelled anything.
SYSTEM_PROMPT = (
    "You are the virtual receptionist for CareDesk Clinic, speaking with a caller on the phone. "
    "Your replies are spoken aloud, so use short, natural sentences. "
    "Never use emojis, bullet points, markdown or any formatting that can't be spoken. "
    "Be warm, calm and concise. Ask one question at a time. "
    "You will soon be able to check doctor availability, book and cancel appointments, "
    "but those tools are not connected yet. Do not claim to have booked, cancelled or "
    "looked up anything. If asked, say that feature is being set up."
)


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing {name}. Add it to server/.env")
    return value


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments) -> None:
    logger.info("Starting bot")

    elevenlabs_key = require_env("ELEVENLABS_API_KEY")
    google_key = require_env("GOOGLE_API_KEY")

    # Speech-to-text (streaming over WebSocket)
    stt = ElevenLabsRealtimeSTTService(api_key=elevenlabs_key)

    # Text-to-speech
    tts = ElevenLabsTTSService(
        api_key=elevenlabs_key,
        settings=ElevenLabsTTSService.Settings(
            voice=os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM"),
        ),
    )

    # LLM (Gemini)
    llm = GoogleInteractionsLLMService(
        api_key=google_key,
        settings=GoogleInteractionsLLMService.Settings(
            model=os.getenv("GOOGLE_MODEL", "gemini-2.5-flash"),
            system_instruction=SYSTEM_PROMPT,
        ),
    )

    context = LLMContext()
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer()),
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
                "content": "Greet the caller as the CareDesk Clinic receptionist in one short "
                "sentence and ask how you can help.",
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
    """Entry point called by the Pipecat runner once per session."""
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