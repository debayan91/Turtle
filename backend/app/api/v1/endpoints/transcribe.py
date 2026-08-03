from fastapi import APIRouter, UploadFile, File
from pydantic import BaseModel

router = APIRouter()


class TranscribeResponse(BaseModel):
    text: str
    language: str = "en"


@router.post("", response_model=TranscribeResponse)
async def transcribe_audio(file: UploadFile = File(...)):
    """
    Audio dictation (Speech-to-Text) endpoint stub.
    """
    # Placeholder for Whisper / STT processing
    filename = file.filename or "audio"
    return TranscribeResponse(
        text=f"Sample transcription content for uploaded file '{filename}'",
        language="en"
    )
