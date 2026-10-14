# ─────────────────────────────────────────────────────────────────
# MaaSakhi Voice Note Handler
# Uses Groq Whisper to transcribe Hindi voice notes
# ─────────────────────────────────────────────────────────────────

import os
import requests
from groq import Groq

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")


def transcribe_voice_note(media_url, twilio_sid, twilio_token):
    """
    Downloads voice note from Twilio and transcribes it using Groq Whisper.
    Returns transcribed text or None if failed.
    """
    try:
        # Step 1 — Download audio from Twilio
        response = requests.get(
            media_url,
            auth=(twilio_sid, twilio_token),
            timeout=30
        )

        if response.status_code != 200:
            print(f"Failed to download audio: {response.status_code}")
            return None

        # Step 2 — Save audio temporarily
        import tempfile
        audio_path = os.path.join(tempfile.gettempdir(), f"voice_note_{os.getpid()}.ogg")
        with open(audio_path, "wb") as f:
            f.write(response.content)

        # Step 3 — Transcribe with Groq Whisper (turbo is ~3x faster)
        client = Groq(api_key=GROQ_API_KEY)

        domain_prompt = "Maternal health consultation. Hindi, Hinglish, English: theek hoon, ab accha lag raha hai, pain, fever, bleeding, delivery, relief."

        try:
            with open(audio_path, "rb") as audio_file:
                transcription = client.audio.transcriptions.create(
                    model="whisper-large-v3-turbo",
                    file=audio_file,
                    prompt=domain_prompt,
                    response_format="text",
                    timeout=15.0
                )
        except Exception as te:
            print(f"Turbo whisper fallback to standard: {te}")
            with open(audio_path, "rb") as audio_file:
                transcription = client.audio.transcriptions.create(
                    model="whisper-large-v3",
                    file=audio_file,
                    prompt=domain_prompt,
                    response_format="text",
                    timeout=20.0
                )

        transcribed_text = str(transcription).strip()
        print(f"Transcribed: {transcribed_text}")

        # Cleanup temp audio
        try:
            if os.path.exists(audio_path):
                os.remove(audio_path)
        except Exception:
            pass

        return transcribed_text

    except Exception as e:
        print(f"Voice transcription error: {e}")
        return None