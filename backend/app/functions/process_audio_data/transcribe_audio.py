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
from pydub import AudioSegment
from io import BytesIO
from pydub.exceptions import CouldntDecodeError
from app.functions.embedding.embedding_model import embedd_transcriptions
from app.domain.store import store
from app.core.config import settings
from whisperx.diarize import DiarizationPipeline

def load_transcription_model():
    new_model = whisperx.load_model(
        settings.transcription_model,
        device,
        compute_type=compute_type,
        language="en",
        download_root=model_dir  # If None, uses default HF cache
    )
    if device == "cuda":
        torch.cuda.empty_cache()
    return new_model


def reload_transcription_model():
    global transcription_model
    transcription_model = load_transcription_model()


def load_diarize_model():
    if not settings.hf_token:
        raise RuntimeError("HF_TOKEN is not set. Please add it to your .env file.")

    new_model = DiarizationPipeline(
        use_auth_token=settings.hf_token,
        device=device
    )
    return new_model


model_dir = os.getenv("WHISPERX_MODELS_DIR", None)
print("WHISPERX_MODELS_DIR:", os.getenv("WHISPERX_MODELS_DIR"))

if model_dir is None:
    # Dev/local environment: auto-detect device
    device = "cuda" if torch.cuda.is_available() else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"
else:
    # Docker: CPU-only setup
    device = "cpu"
    compute_type = "int8"
    print("Warning: With Docker currently only CPU support is possible")

print(f"Loading transcription and alignment models on device: {device} with compute type: {compute_type}")

# Use a dictionary to cache alignment models by language to avoid reloading
alignment_models_cache = {}

# 1. Load models
transcription_model = load_transcription_model()
diarize_model = load_diarize_model()
print("Models loaded successfully.")



def decode_audio_bytes(
    audio_bytes: bytes,
    content_type: str | None = None,
) -> AudioSegment:
    """
    Decode audio bytes safely.

    Tries the format from the MIME type first, then lets FFmpeg
    detect the format automatically.
    """

    if not audio_bytes:
        raise RuntimeError("The audio data is empty.")

    normalized_content_type = (content_type or "").casefold()

    possible_formats: list[str] = []

    if "webm" in normalized_content_type:
        possible_formats.append("webm")

    if "ogg" in normalized_content_type:
        possible_formats.append("ogg")

    if "mpeg" in normalized_content_type or "mp3" in normalized_content_type:
        possible_formats.append("mp3")

    if "wav" in normalized_content_type:
        possible_formats.append("wav")

    if "mp4" in normalized_content_type:
        possible_formats.append("mp4")

    if "m4a" in normalized_content_type:
        possible_formats.append("m4a")

    for audio_format in possible_formats:
        try:
            return AudioSegment.from_file(
                BytesIO(audio_bytes),
                format=audio_format,
            )
        except CouldntDecodeError:
            continue

    try:
        return AudioSegment.from_file(
            BytesIO(audio_bytes)
        )
    except CouldntDecodeError as error:
        raise RuntimeError(
            "The audio could not be decoded. "
            "Please use a valid WAV, MP3, OGG, WebM, M4A, or MP4 file."
        ) from error





async def transcribe_audio(
    audio_bytes: bytes,
    content_type: str,
    batch_size: int = 16,
    time_offset: float = 0.0,
):
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

    players = await store.list_players()
    print(len(players))

    combined_audio = AudioSegment.silent(duration=1000)
    speaker_order: list[str] = []

    for player in players:
        if player.voiceprint is None:
            continue

        voice_bytes = player.voiceprint.audio_bytes

        if not voice_bytes:
            print(
                f"Skipping empty voiceprint for player: {player.name}"
            )
            continue

        try:
            voice_note = decode_audio_bytes(
                voice_bytes
            )
        except RuntimeError as error:
            print(
                f"Skipping invalid voiceprint for "
                f"{player.name}: {error}"
            )
            continue

        combined_audio += (
            voice_note
            + AudioSegment.silent(duration=500)
        )

        speaker_order.append(player.name)

    session_audio = decode_audio_bytes(
    audio_bytes,
    content_type=content_type,
)
    intro_duration_ms = len(combined_audio)
    combined_audio += session_audio
    # export
    output_buffer = BytesIO()
    combined_audio.export(output_buffer, format="wav")
    output_buffer.seek(0)

    print("Combining player voice notes with session audio...")
    combined_audio_buffer = output_buffer
    intro_duration_s = intro_duration_ms / 1000  # Umwandeln in Sekunden

    speaker_map = {f"SPEAKER_{i:02d}": name for i, name in enumerate(speaker_order)}
    print(speaker_map)

    print("Loading audio...")

    # 2. Save bytes to a temporary file (required by whisperx.load_audio)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tempAudio:
        tempAudio.write(combined_audio_buffer.read())
        tempAudio.flush()
        tempAudioPath = tempAudio.name

    try:
        # Load audio from the temporary file
        audio = whisperx.load_audio(tempAudioPath)

        # 3. Transcribe using the cached model
        result = transcription_model.transcribe(audio, batch_size=batch_size, language="en",)
        # print("Transcription segments:", result["segments"])

        # 4. Align whisper output to improve the word-level timestamps in transcription.
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

        # 5. Perform alignment
        print("Aligning...")
        resultA = whisperx.align(result["segments"], alignment_model, metadata, audio, device,
                                 return_char_alignments=False)
        # print("Aligned segments:", resultA["segments"])


        # 6. Assign speaker labels
        print("Assigning speakers...")

        # Min players is guaranteed to be available based on the user's requirement.
        min_players = max(len(speaker_order), 1)
        max_players = max(min_players + 2, store.group.max_size)
        print(f"min players: {min_players}")
        print(f"max players: {max_players}")

        # Perform diarization with constraints
        diarizeSegments = diarize_model(audio, min_speakers=min_players, max_speakers=max_players)

        # Assign speakers to the aligned segments
        resultB = whisperx.assign_word_speakers(diarizeSegments, resultA)

        # print("Diarization segments:", diarizeSegments)

        # The final segments are the diarized result

        for segment in resultB.get("segments", []):
            original_speaker = segment.get(
                "speaker",
                "unknown",
            )

            print(original_speaker)

            if original_speaker in speaker_map:
                player_name = speaker_map[original_speaker]

            elif len(speaker_order) == 1:
                # During a single-player test, assign unmatched speech
                # to the only registered player.
                player_name = speaker_order[0]

            else:
                # With multiple players, do not guess.
                player_name = "unknown"

            segment["player_name"] = player_name
            segment["speaker"] = player_name

            print("playername:", player_name)

        # print results
        for seg in resultB.get("segments", []):
            print(
                f"[{seg['start']:.2f}s – {seg['end']:.2f}s] "
                f"{seg['speaker']}: {seg['text']}"
            )

        # remove voice notes
        filtered_segments = [seg for seg in resultB["segments"] if seg["start"] > intro_duration_s]

        # 7. Embed the resulting text

        
        # texts = []
        # speakers = []

        # for seg in filtered_segments:
        #     text = seg.get("text", "").strip()
        #     if not text:
        #         continue

        #     texts.append(text)
        #     speakers.append(seg.get("speaker", "unknown"))

        # if texts:
        #     embedd_transcriptions(
        #         embedding_text=texts,
        #         speakers=speakers
        #     )

        # print(f"Removed intro (first {intro_duration_s:.2f} seconds). Remaining segments: {len(filtered_segments)}")


        texts: list[str] = []
        speakers: list[str] = []
        start_times: list[float] = []
        end_times: list[float] = []

        for seg in filtered_segments:
            text = seg.get("text", "").strip()

            if not text:
                continue
            
            texts.append(text)
            speakers.append(seg.get("speaker", "unknown"))

            # WhisperX timestamps include the voiceprint introduction.
            # Remove that introduction so timestamps begin at the actual session.
            start_times.append(
                max(
                    0.0,
                    float(seg.get("start", 0.0))
                    - intro_duration_s
                    + time_offset,
                )
            )

            end_times.append(
                max(
                    0.0,
                    float(seg.get("end", 0.0))
                    - intro_duration_s
                    + time_offset,
                )
            )

        if texts:
            embedd_transcriptions(
                embedding_text=texts,
                speakers=speakers,
                start_times=start_times,
                end_times=end_times,
            )

        session_segments = []

        for segment in filtered_segments:
            normalized_segment = dict(segment)

            normalized_segment["start"] = max(
                0.0,
                float(segment.get("start", 0.0))
                - intro_duration_s
                + time_offset,
            )
            
            normalized_segment["end"] = max(
                0.0,
                float(segment.get("end", 0.0))
                - intro_duration_s
                + time_offset,
            )

            session_segments.append(normalized_segment)

        return session_segments

        #return filtered_segments

        # # Return the diarized segments
        # return final_segments

    except Exception as e:
        print(f"An error occurred during transcription: {e}")
        raise RuntimeError(
            f"Audio transcription failed: {e}"
        ) from e
    
    finally:
        # Clean up the temporary file
        os.remove(tempAudioPath)

