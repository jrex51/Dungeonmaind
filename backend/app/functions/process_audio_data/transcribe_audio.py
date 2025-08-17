#WhisperX is not compatible with python3.13.
#It requires: Python 3.12
#ffmpeg installation necessary
#For GPU support:   https://developer.nvidia.com/cuda-12-8-1-download-archive (CUDA Toolkit 12.8.1)
#                   https://developer.nvidia.com/cudnn-downloads (cuDNN 9.10.2)
#                   (ctranslate2==4.6.0)
#                   pip uninstall torch torchaudio
#                   pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu128

import torch
import whisperx
import tempfile

from app.core.config import settings

def transcribe_audio(audio_bytes: bytes, batch_size=16):

    #set default device to GPU
    device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cuda":
        compute_type = "float16"
    else:
        compute_type = "int8"

    # 1. Load the model
    print("Loading WhisperX")
    model = whisperx.load_model(settings.transcription_model, device, compute_type=compute_type)
    # save model to local path (optional)
    # model_dir = "/path/"
    # model = whisperx.load_model("large-v2", device, compute_type=compute_type, download_root=model_dir)

    # 2. Save bytes to a temporary file (required by whisperx.load_audio)
    print("Loading audio...")
    with tempfile.NamedTemporaryFile(suffix=".mp3",delete=False) as temp_audio:
        temp_audio.write(audio_bytes)
        temp_audio.flush()
        audio = whisperx.load_audio(temp_audio.name)

    # 3. Transcribe
    result = model.transcribe(audio, batch_size=batch_size)
    print(result["segments"])
    # delete model if low on GPU resources
    # import gc; import torch; gc.collect(); torch.cuda.empty_cache(); del model

    # 4. Align whisper output to improve the word-level timestamps in your transcription.
    print("Aligning...")
    model_a, metadata = whisperx.load_align_model(language_code=result["language"], device=device)
    result_a = whisperx.align(result["segments"], model_a, metadata, audio, device, return_char_alignments=False)
    print(result_a["segments"])
    # 5. Assign speaker labels

    #created a HF token and then added it
    diarize_model = whisperx.diarize.DiarizationPipeline(use_auth_token="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", device=device)

    # add min/max number of speakers if known
    diarize_segments = diarize_model(audio)
    # diarize_model(audio, min_speakers=min_speakers, max_speakers=max_speakers)

    result_b = whisperx.assign_word_speakers(diarize_segments, result_a)
    print(diarize_segments)
    print(result_b["segments"]) # segments are now assigned speaker IDs

    return result_b["segments"]