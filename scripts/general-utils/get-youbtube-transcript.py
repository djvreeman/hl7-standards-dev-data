import sys
import os
import json
import requests
from youtube_transcript_api import YouTubeTranscriptApi

CONFIG_PATH = "data/config/config.json"

def load_api_key(config_path):
    """
    Loads the YouTube API key from the specified JSON configuration file.
    :param config_path: Path to the configuration file.
    :return: The YouTube API key as a string.
    """
    try:
        with open(config_path, 'r', encoding='utf-8') as config_file:
            config = json.load(config_file)
        return config.get("youtube_api_key", None)
    except Exception as e:
        print(f"Error loading API key from {config_path}: {e}")
        sys.exit(1)

def fetch_transcript(video_id, include_timestamps):
    """
    Fetches the transcript of a YouTube video.
    :param video_id: The YouTube video ID.
    :param include_timestamps: Whether to include timestamps in the transcript.
    :return: A formatted transcript as a string.
    """
    try:
        transcript = YouTubeTranscriptApi.get_transcript(video_id)
        if include_timestamps:
            return "\n".join(
                [f"[{entry['start']:.2f}] {entry['text']}" for entry in transcript]
            )
        else:
            return "\n".join([entry["text"] for entry in transcript])
    except Exception as e:
        print(f"Error fetching transcript: {e}")
        sys.exit(1)

def fetch_video_metadata(video_id, api_key):
    """
    Fetches the title and description of a YouTube video using YouTube Data API.
    :param video_id: The YouTube video ID.
    :param api_key: The YouTube API key.
    :return: A tuple containing the video title and description.
    """
    url = f"https://www.googleapis.com/youtube/v3/videos?part=snippet&id={video_id}&key={api_key}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        if "items" in data and len(data["items"]) > 0:
            snippet = data["items"][0]["snippet"]
            return snippet["title"], snippet["description"]
        else:
            return f"Video Title for ID: {video_id}", "Description unavailable."
    except Exception as e:
        print(f"Error fetching video metadata: {e}")
        return f"Video Title for ID: {video_id}", "Description unavailable."

def save_to_markdown(video_id, video_title, video_description, transcript, output_folder):
    """
    Saves the transcript to a markdown file.
    :param video_id: The YouTube video ID.
    :param video_title: The title of the video.
    :param video_description: The description of the video.
    :param transcript: The transcript text.
    :param output_folder: The folder where the markdown file will be saved.
    """
    os.makedirs(output_folder, exist_ok=True)
    output_file = os.path.join(output_folder, f"{video_id}-transcript.md")
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    
    try:
        with open(output_file, 'w', encoding='utf-8') as file:
            file.write(f"# {video_title}\n")
            file.write("## Source\n")
            file.write(f"Transcript for YouTube Video: [{video_id}]({video_url})\n\n")
            file.write("## Description\n")
            file.write(f"{video_description}\n\n")
            file.write("## Transcript\n")
            file.write(transcript)
        print(f"Transcript saved to {output_file}")
    except Exception as e:
        print(f"Error saving transcript: {e}")
        sys.exit(1)

def main():
    """
    Main function to fetch transcript and save as markdown.
    """
    if len(sys.argv) < 2:
        print("Usage: python script.py <YouTube Video ID> [output_folder] [--timestamps]")
        sys.exit(1)
    
    video_id = sys.argv[1]
    output_folder = sys.argv[2] if len(sys.argv) > 2 else "."
    include_timestamps = "--timestamps" in sys.argv

    print("Loading API key...")
    api_key = load_api_key(CONFIG_PATH)
    if not api_key:
        print("Error: YouTube API key not found in configuration file.")
        sys.exit(1)

    print("Fetching video metadata...")
    video_title, video_description = fetch_video_metadata(video_id, api_key)
    
    print("Fetching transcript...")
    transcript = fetch_transcript(video_id, include_timestamps)
    
    print("Saving transcript...")
    save_to_markdown(video_id, video_title, video_description, transcript, output_folder)

if __name__ == "__main__":
    main()