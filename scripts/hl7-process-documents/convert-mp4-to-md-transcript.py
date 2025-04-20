#!/usr/bin/env python3

import os
import ffmpeg
from faster_whisper import WhisperModel
from resemblyzer import preprocess_wav, VoiceEncoder
from sklearn.cluster import KMeans
import numpy as np

# ---- Configuration Defaults ----
DEFAULT_OUTPUT_DIR = "output"
DEFAULT_AUDIO_FILENAME = "audio.wav"
DEFAULT_TRANSCRIPT_FILENAME = "transcript.md"
DEFAULT_MODEL_SIZE = "small"  # Options: 'tiny', 'base', 'small', 'medium', 'large'

BLOCK_SECONDS = 30  # Group transcript by 30-second blocks
SPEAKER_COUNT = 2   # Number of fake speakers to rotate
LONG_PAUSE_SECONDS = 5  # Pause threshold between captions for paragraph break

# ---- Helper Functions ----

def extract_audio(video_path, audio_path):
    print(f"🎬 Extracting audio from {video_path} using ffmpeg-python...")
    try:
        (
            ffmpeg
            .input(video_path)
            .output(audio_path, acodec='pcm_s16le', ac=1, ar='16000')
            .run(overwrite_output=True, quiet=True)
        )
    except ffmpeg.Error as e:
        print(f"❌ ffmpeg error: {e}")
        raise
    print(f"🎧 Audio extracted to {audio_path}")

def format_timestamp(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours:02}:{minutes:02}:{secs:06.3f}".replace('.', ',')

def analyze_speakers(audio_path, expected_num_speakers=2):
    print(f"🎤 Analyzing speakers from {audio_path}...")

    wav = preprocess_wav(audio_path)
    encoder = VoiceEncoder()

    result = encoder.embed_utterance(wav, return_partials=True)

    if isinstance(result, tuple) and len(result) == 2:
        partial_embeds, partial_times = result
    else:
        partial_embeds = result
        partial_times = None

    valid_embeds = []
    valid_times = []

    for idx, embed in enumerate(partial_embeds):
        embed = np.array(embed)
        if embed.ndim == 1 and embed.shape[0] == 256:
            valid_embeds.append(embed)
            if partial_times:
                valid_times.append(partial_times[idx])

    if not valid_embeds:
        raise ValueError("No valid embeddings found for speaker analysis.")

    partial_embeds = np.vstack(valid_embeds)

    # 🛡️ NEW: Handle too few samples
    num_samples = len(partial_embeds)
    num_clusters = min(expected_num_speakers, num_samples)

    if num_clusters <= 1:
        print(f"⚠️ Only one speaker detected or insufficient samples, defaulting to Speaker 1.")
        labels = np.zeros(num_samples, dtype=int)
    else:
        kmeans = KMeans(n_clusters=num_clusters, random_state=0).fit(partial_embeds)
        labels = kmeans.labels_

    speaker_times = []
    if partial_times and valid_times:
        for (start, end), label in zip(valid_times, labels):
            speaker_times.append((start, end, label))
    else:
        audio_duration = len(wav) / 16000
        time_per_embed = audio_duration / len(labels)
        for i, label in enumerate(labels):
            start = i * time_per_embed
            end = (i + 1) * time_per_embed
            speaker_times.append((start, end, label))

    return speaker_times

def transcribe_audio(audio_path, output_dir, model_size=DEFAULT_MODEL_SIZE):
    print(f"📝 Transcribing audio with Faster-Whisper ({model_size} model)...")
    model = WhisperModel(model_size, device="auto", compute_type="auto")
    
    segments, info = model.transcribe(audio_path, beam_size=5, word_timestamps=False)

    vtt_output_path = os.path.join(output_dir, "audio.vtt")

    with open(vtt_output_path, "w") as f:
        f.write("WEBVTT\n\n")
        for segment in segments:
            start = format_timestamp(segment.start)
            end = format_timestamp(segment.end)
            text = segment.text.strip()
            f.write(f"{start} --> {end}\n{text}\n\n")

    return vtt_output_path

def parse_vtt_blocks(vtt_file, block_seconds=30, long_pause_seconds=5):
    def parse_timestamp(ts):
        ts = ts.replace(',', '.').strip()
        parts = ts.split(':')

        if len(parts) == 3:
            h, m, s = parts
            seconds = int(h) * 3600 + int(m) * 60 + float(s)
        elif len(parts) == 2:
            m, s = parts
            seconds = int(m) * 60 + float(s)
        else:
            raise ValueError(f"Unexpected timestamp format: {ts}")

        return seconds

    print(f"📚 Parsing VTT blocks from {vtt_file}...")
    blocks = {}
    previous_time = 0

    with open(vtt_file, 'r') as f:
        lines = [line.strip() for line in f if line.strip()]

    for i, line in enumerate(lines):
        if "-->" in line:
            start_ts = line.split("-->")[0].strip()
            start_sec = parse_timestamp(start_ts)
            block_index = int(start_sec // block_seconds)

            gap = start_sec - previous_time
            paragraph_break = gap > long_pause_seconds
            previous_time = start_sec

            if i + 1 < len(lines):
                text_line = lines[i + 1]
            else:
                continue

            if block_index not in blocks:
                blocks[block_index] = []

            blocks[block_index].append((text_line, paragraph_break))

    return blocks

def format_blocks_as_markdown(blocks, speaker_times, block_seconds=30):
    output = "# Transcript\n\n"
    speaker_labels = {0: "Speaker 1", 1: "Speaker 2", 2: "Speaker 3", 3: "Speaker 4"}  # Expandable if needed

    def find_speaker_for_time(start_sec):
        # Find the closest speaker label for the given start time
        for start, end, speaker in speaker_times:
            if start <= start_sec <= end:
                return speaker
        # Default if not found
        return 0

    for block_index, entries in sorted(blocks.items()):
        block_start_time = block_index * block_seconds
        minutes, seconds = divmod(block_start_time, 60)
        timestamp = f"[{int(minutes):02}:{int(seconds):02}]"

        speaker_id = find_speaker_for_time(block_start_time)
        speaker = speaker_labels.get(speaker_id, f"Speaker {speaker_id+1}")

        output += f"{timestamp} **{speaker}**:\n\n"

        paragraph = ""
        for text, paragraph_break in entries:
            if paragraph_break and paragraph:
                output += paragraph.strip() + "\n\n"
                paragraph = ""
            paragraph += text + " "

        if paragraph:
            output += paragraph.strip() + "\n\n"

    return output
# ---- Main Program ----

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Extract audio and transcribe a local MP4 file to Markdown using Faster-Whisper and smart speaker detection.")
    parser.add_argument('--input', '-i', required=True, help='Path to the local MP4 file')
    parser.add_argument('--output', '-o', help='Path to output Markdown file (optional)', default=None)
    parser.add_argument('--model', '-m', help='Whisper model size (tiny, base, small, medium, large)', default=DEFAULT_MODEL_SIZE)
    parser.add_argument('--speakers', '-s', type=int, help='Expected number of speakers (default=2)', default=2)
    args = parser.parse_args()

    video_path = args.input
    model_size = args.model
    expected_num_speakers = args.speakers

    # Determine output paths
    if args.output:
        transcript_path = args.output
        output_dir = os.path.dirname(transcript_path) or DEFAULT_OUTPUT_DIR
    else:
        output_dir = DEFAULT_OUTPUT_DIR
        transcript_path = os.path.join(output_dir, DEFAULT_TRANSCRIPT_FILENAME)

    os.makedirs(output_dir, exist_ok=True)
    audio_path = os.path.join(output_dir, DEFAULT_AUDIO_FILENAME)

    try:
        # 1. Extract audio
        extract_audio(video_path, audio_path)

        # 2. Analyze speakers
        speaker_times = analyze_speakers(audio_path, expected_num_speakers=expected_num_speakers)

        # 3. Transcribe audio
        vtt_file = transcribe_audio(audio_path, output_dir, model_size=model_size)

        # 4. Parse transcript blocks
        blocks = parse_vtt_blocks(vtt_file, block_seconds=BLOCK_SECONDS, long_pause_seconds=LONG_PAUSE_SECONDS)

        # 5. Generate Markdown
        markdown = format_blocks_as_markdown(blocks, speaker_times, block_seconds=BLOCK_SECONDS)

        # 6. Write Markdown to output
        with open(transcript_path, 'w') as f:
            f.write(markdown)

        print(f"\n✅ Transcript saved at {transcript_path}")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()