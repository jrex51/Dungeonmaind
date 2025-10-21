# WhisperX is not compatible with python3.13.
# It requires: Python 3.12
# ffmpeg installation necessary
# For GPU support:   https://developer.nvidia.com/cuda-12-8-1-download-archive (CUDA Toolkit 12.8.1)
#                   https://developer.nvidia.com/cudnn-downloads (cuDNN 9.10.2)
#                   (ctranslate2==4.6.0)
#                   pip uninstall torch torchaudio
#                   pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu128

import torch
import whisperx
import tempfile
import os

from app.functions.embedding.embedding_model import embedd_transcriptions
from app.domain.store import store
from app.core.config import settings

# Load models once at startup.
try:
    device = "cuda" if torch.cuda.is_available() else "cpu"
    computeType = "float16" if device == "cuda" else "int8"
    print(f"Loading transcription and alignment models on device: {device} with compute type: {computeType}")

    # 1. Load the transcription model
    transcription_model = whisperx.load_model(
        settings.transcription_model,
        device,
        compute_type=computeType,
        download_root=os.getenv("WHISPERX_MODELS_DIR", None)
    )

    # Use a dictionary to cache alignment models by language to avoid reloading
    alignment_models_cache = {}

    # 2. Load the diarization model
    # created an HF token and then added it
    diarize_model = whisperx.diarize.DiarizationPipeline(
        use_auth_token="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",
        device=device
    )

    print("Models loaded successfully.")
except Exception as e:
    print(f"Error loading models: {e}")
    transcription_model = None
    alignment_models_cache = {}
    diarize_model = None


def transcribe_audio(audio_bytes: bytes, content_type: str, batch_size=16):
    # Check if models are loaded before proceeding
    if not transcription_model or not diarize_model:
        print("Error: Models are not loaded. Transcription aborted.")
        return None

    # Robust content type parsing and saving bytes to a temporary file
    file_extension_map = {
        'ogg': 'ogg',
        'webm': 'webm',
        'wav': 'wav',
        'mpeg': 'mp3',
        'mp4': 'mp4'
    }
    fileExtension = 'webm'
    for key in file_extension_map:
        if key in content_type:
            fileExtension = file_extension_map[key]
            break

    print("Loading audio...")
    # 3. Save bytes to a temporary file (required by whisperx.load_audio)
    with tempfile.NamedTemporaryFile(suffix=f".{fileExtension}", delete=False) as tempAudio:
        tempAudio.write(audio_bytes)
        tempAudio.flush()
        tempAudioPath = tempAudio.name

    try:
        # Load audio from the temporary file
        audio = whisperx.load_audio(tempAudioPath)

        # 4. Transcribe using the cached model
        result = transcription_model.transcribe(audio, batch_size=batch_size)
        print("Transcription segments:", result["segments"])

        # 5. Align whisper output to improve the word-level timestamps in your transcription.
        language_code = result["language"]
        if language_code not in alignment_models_cache:
            print(f"Loading alignment model for language: {language_code}...")
            alignment_model, metadata = whisperx.load_align_model(
                language_code=language_code,
                device=device
            )
            alignment_models_cache[language_code] = (alignment_model, metadata)
        else:
            print(f"Using cached alignment model for language: {language_code}.")
            alignment_model, metadata = alignment_models_cache[language_code]

        # 6. Perform alignment
        print("Aligning...")
        resultA = whisperx.align(result["segments"], alignment_model, metadata, audio, device,
                                 return_char_alignments=False)
        print("Aligned segments:", resultA["segments"])

        texts = [segment['text'] for segment in resultA["segments"]]

        # 7. Embed the resulting text
        if texts and any(text.strip() for text in texts):
            print(texts)
            embedd_transcriptions(texts)

        # 8. Assign speaker labels
        print("Assigning speakers...")

        # Max players is guaranteed to be available based on the user's requirement.
        max_players = store.group.max_size

        # Perform diarization with constraints
        diarizeSegments = diarize_model(audio, min_speakers=1, max_speakers=max_players)

        # Assign speakers to the aligned segments
        resultB = whisperx.assign_word_speakers(diarizeSegments, resultA)

        print("Diarization segments:", diarizeSegments)
        print("Final segments (Diarized):", resultB["segments"])

        # The final segments are the diarized result
        final_segments = resultB["segments"]

        # Return the diarized segments
        return final_segments


    except Exception as e:
        print(f"An error occurred during transcription: {e}")
        return None

    finally:
        # Clean up the temporary file
        os.remove(tempAudioPath)