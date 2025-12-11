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
import glob


from app.functions.embedding.embedding_model import embedd_transcriptions
from app.domain.store import store
from app.core.config import settings
from whisperx.diarize import DiarizationPipeline

def load_transcription_model():
    new_model = whisperx.load_model(
        settings.transcription_model,
        device,
        compute_type=compute_type,
        download_root=model_dir # If None, uses default HF cache
    )
    if device == "cuda":
        torch.cuda.empty_cache()
    return new_model

def reload_transcription_model():
    global transcription_model
    transcription_model = load_transcription_model()

def load_diarize_model():
    # created an HF token and then added it
    new_model = (DiarizationPipeline(
        use_auth_token="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",
        device=device
    ))
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

async def transcribe_audio(audio_bytes: bytes, content_type: str, batch_size=16):
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
    
    print("check players list")

    players = await store.list_players()
    print(len(players))

    combined_audio = AudioSegment.silent(duration=1000) 
    speaker_order = [] # Kombiniere alle Voiceprints aus dem Store 
    for p in players: 
        if p.voiceprint is None: 
            continue # Spieler ohne Voiceprint überspringen 

        voice_bytes = p.voiceprint.audio_bytes 
        note = AudioSegment.from_file(BytesIO(voice_bytes)) 
        combined_audio += note + AudioSegment.silent(duration=500) 
        speaker_order.append(p.name) #Kombiniere die Session-Aufnahme 
    
    session_audio = AudioSegment.from_file(BytesIO(audio_bytes)) 
    intro_duration_ms = len(combined_audio) 
    combined_audio += session_audio
    #export
    output_buffer = BytesIO() 
    combined_audio.export(output_buffer, format="wav") 
    output_buffer.seek(0)

    print("Combining player voice notes with session audio...")
    combined_audio_buffer = output_buffer
    intro_duration_s = intro_duration_ms / 1000  #Umwandeln in Sekunden

    speaker_map = {f"SPEAKER_{i:02d}": name for i, name in enumerate(speaker_order)} 
    print(speaker_map)

    print("Loading audio...")
  
    # 2. Save bytes to a temporary file (required by whisperx.load_audio)
    with tempfile.NamedTemporaryFile(suffix=f".{fileExtension}", delete=False) as tempAudio:
        tempAudio.write(combined_audio_buffer.read())
        tempAudio.flush()
        tempAudioPath = tempAudio.name

    try:
        # Load audio from the temporary file
        audio = whisperx.load_audio(tempAudioPath)

        # 3. Transcribe using the cached model
        result = transcription_model.transcribe(audio, batch_size=batch_size)
        #print("Transcription segments:", result["segments"])

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
        #print("Aligned segments:", resultA["segments"])

        texts = [segment['text'] for segment in resultA["segments"]]

        # 6. Embed the resulting text
        if texts and any(text.strip() for text in texts):
            print(texts)
            embedd_transcriptions(texts)

        # 7. Assign speaker labels
        #print("Assigning speakers...")

        # Max players is guaranteed to be available based on the user's requirement.
        max_players = store.group.max_size

        # Perform diarization with constraints
        diarizeSegments = diarize_model(audio, min_speakers=1, max_speakers=max_players)

        # Assign speakers to the aligned segments
        resultB = whisperx.assign_word_speakers(diarizeSegments, resultA)

        # print("Diarization segments:", diarizeSegments)

        # The final segments are the diarized result

        for segment in resultB["segments"]:
    
            original_speaker = segment["speaker"]
            print(original_speaker)
            player_name = speaker_map.get(original_speaker, "unkown")
            #print("segment playername:", segment["player_name"])
            segment["player_name"] = player_name
            print("playername:", player_name)
            segment["speaker"] = player_name
        
        final_segments = resultB["segments"]

        #remove voice notes
        filtered_segments = [seg for seg in resultB["segments"] if seg["start"] > intro_duration_s]

        #print("Final segments (Diarized):", filtered_segments)

        for seg in filtered_segments:
            print(
                f"[{seg['start']:.2f}s – {seg['end']:.2f}s] "
                f"{seg['speaker']}: {seg['text']}"
        )
        #print(f"Removed intro (first {intro_duration_s:.2f} seconds). Remaining segments: {len(filtered_segments)}")

        return filtered_segments

        # # Return the diarized segments
        # return final_segments


    except Exception as e:
        print(f"An error occurred during transcription: {e}")
        return None

    finally:
        # Clean up the temporary file
        os.remove(tempAudioPath)

