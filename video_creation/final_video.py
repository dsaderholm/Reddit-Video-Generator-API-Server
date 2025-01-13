import multiprocessing
import os
import re
import tempfile
import textwrap
import threading
import time
from os.path import exists
from pathlib import Path
from typing import Dict, Final, Tuple

import ffmpeg
import translators
from PIL import Image, ImageDraw, ImageFont
from rich.console import Console
from rich.progress import track
from tqdm import tqdm

from utils import settings
from utils.cleanup import cleanup
from utils.console import print_step, print_substep
from utils.fonts import getheight
from utils.thumbnail import create_thumbnail
from utils.videos import save_data

console = Console()

def verify_files_exist(reddit_id: str, number_of_clips: int, is_story_mode: bool) -> None:
    """Verify all required files exist before processing.
    
    Args:
        reddit_id (str): The reddit post ID
        number_of_clips (int): Number of clips to process
        is_story_mode (bool): Whether story mode is enabled
    
    Raises:
        FileNotFoundError: If any required files are missing
    """
    required_files = []
    # Add audio files
    required_files.append(f"assets/temp/{reddit_id}/audio.mp3")
    required_files.append(f"assets/temp/{reddit_id}/background.mp4")
    
    # Add image files
    if is_story_mode:
        required_files.append(f"assets/temp/{reddit_id}/png/title.png")
        for i in range(number_of_clips + 1):
            required_files.append(f"assets/temp/{reddit_id}/mp3/postaudio-{i}.mp3")
    else:
        required_files.append(f"assets/temp/{reddit_id}/mp3/title.mp3")
        for i in range(number_of_clips):
            required_files.append(f"assets/temp/{reddit_id}/mp3/{i}.mp3")
            required_files.append(f"assets/temp/{reddit_id}/png/comment_{i}.png")
    
    missing_files = [f for f in required_files if not os.path.exists(f)]
    if missing_files:
        raise FileNotFoundError(f"Missing required files: {missing_files}")

def try_ffmpeg_output(background_clip, final_audio, path: str, progress_file: str, max_retries: int = 3) -> bool:
    """Attempt to run ffmpeg output with retries.
    
    Args:
        background_clip: The background video clip
        final_audio: The final audio track
        path (str): Output file path
        progress_file (str): Path to progress file
        max_retries (int, optional): Maximum number of retry attempts. Defaults to 3.
    
    Returns:
        bool: True if successful
        
    Raises:
        ffmpeg.Error: If all retry attempts fail
    """
    for attempt in range(max_retries):
        try:
            # Leave one CPU core free to prevent resource exhaustion
            threads = max(1, multiprocessing.cpu_count() - 1)
            
            ffmpeg.output(
                background_clip,
                final_audio,
                path,
                f="mp4",
                **{
                    "c:v": "h264",
                    "b:v": "20M",
                    "b:a": "192k",
                    "threads": threads,
                },
            ).overwrite_output().global_args("-progress", progress_file).run(
                quiet=True,
                overwrite_output=True,
                capture_stdout=True,
                capture_stderr=True,
            )
            return True
        except ffmpeg.Error as e:
            print(f"Attempt {attempt + 1} failed:")
            print("Error:", e.stderr.decode("utf8") if e.stderr else "No error details available")
            if attempt == max_retries - 1:
                raise
            print(f"Retrying in 1 second... ({attempt + 1}/{max_retries})")
            time.sleep(1)
    return False

class ProgressFfmpeg(threading.Thread):
    def __init__(self, vid_duration_seconds, progress_update_callback):
        threading.Thread.__init__(self, name="ProgressFfmpeg")
        self.stop_event = threading.Event()
        self.output_file = tempfile.NamedTemporaryFile(mode="w+", delete=False)
        self.vid_duration_seconds = vid_duration_seconds
        self.progress_update_callback = progress_update_callback

    def run(self):
        while not self.stop_event.is_set():
            latest_progress = self.get_latest_ms_progress()
            if latest_progress is not None:
                completed_percent = latest_progress / self.vid_duration_seconds
                self.progress_update_callback(completed_percent)
            time.sleep(1)

    def get_latest_ms_progress(self):
        try:
            self.output_file.seek(0)
            lines = self.output_file.readlines()
            
            if lines:
                for line in lines:
                    if "out_time_ms" in line:
                        out_time_ms_str = line.split("=")[1].strip()
                        if out_time_ms_str.isnumeric():
                            return float(out_time_ms_str) / 1000000.0
                        return None
            return None
        except Exception as e:
            print(f"Error reading progress: {e}")
            return None

    def stop(self):
        self.stop_event.set()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args, **kwargs):
        self.stop()

def name_normalize(name: str) -> str:
    """Normalize a filename to be safe for all operating systems."""
    # Remove null bytes and control characters
    name = re.sub(r'[\x00-\x1F\x7F]', '', name)
    
    # Remove zero-width and other invisible Unicode chars
    name = re.sub(r'[\u200B-\u200F\uFEFF]', '', name)
    
    # Normalize all types of spaces to single space
    name = re.sub(r'\s+', ' ', name)
    name = name.strip()
    
    # Remove forward slashes and backslashes
    name = re.sub(r'[/\\\\]', '', name)
    
    # Handle common shorthand replacements
    name = re.sub(r'( [w,W]\s?\/\s?[o,O,0])', r' without', name)
    name = re.sub(r'( [w,W]\/)', r' with', name)
    name = re.sub(r'(\d+)\s?\/\s?(\d+)', r'\1 of \2', name)
    name = re.sub(r'(\w+)\s?\/\s?(\w+)', r'\1 or \2', name)
    
    # Ensure filename doesn't exceed maximum byte length for Linux
    while len(name.encode('utf-8')) > 255:
        name = name[:-1]
    
    return name

def prepare_background(reddit_id: str, W: int, H: int) -> str:
    """Prepare the background video by cropping to correct aspect ratio."""
    output_path = f"assets/temp/{reddit_id}/background_noaudio.mp4"
    output = (
        ffmpeg.input(f"assets/temp/{reddit_id}/background.mp4")
        .filter("crop", f"ih*({W}/{H})", "ih")
        .output(
            output_path,
            an=None,
            **{
                "c:v": "h264",
                "b:v": "20M",
                "b:a": "192k",
                "threads": max(1, multiprocessing.cpu_count() - 1),
            },
        )
        .overwrite_output()
    )
    try:
        output.run(quiet=True)
    except ffmpeg.Error as e:
        print("Error preparing background:")
        print(e.stderr.decode("utf8") if e.stderr else "No error details available")
        raise
    return output_path

def create_fancy_thumbnail(image, text, text_color, padding, wrap=35):
    """Create a fancy thumbnail with text overlay."""
    print_step(f"Creating fancy thumbnail for: {text}")
    font_title_size = 47
    font = ImageFont.truetype(os.path.join("fonts", "Roboto-Bold.ttf"), font_title_size)
    image_width, image_height = image.size
    lines = textwrap.wrap(text, width=wrap)
    y = (
        (image_height / 2)
        - (((getheight(font, text) + (len(lines) * padding) / len(lines)) * len(lines)) / 2)
        + 30
    )
    draw = ImageDraw.Draw(image)

    username_font = ImageFont.truetype(os.path.join("fonts", "Roboto-Bold.ttf"), 30)
    draw.text(
        (205, 825),
        settings.config["settings"]["channel_name"],
        font=username_font,
        fill=text_color,
        align="left",
    )

    # Adjust font size based on text length
    if len(lines) >= 3:
        lines = textwrap.wrap(text, width=wrap + 10)
        font_title_size = 40 if len(lines) == 3 else 35 if len(lines) == 4 else 30
        font = ImageFont.truetype(os.path.join("fonts", "Roboto-Bold.ttf"), font_title_size)
        y_adjustment = 35 if len(lines) == 3 else 40 if len(lines) == 4 else 30
        y = (
            (image_height / 2)
            - (((getheight(font, text) + (len(lines) * padding) / len(lines)) * len(lines)) / 2)
            + y_adjustment
        )

    for line in lines:
        draw.text((120, y), line, font=font, fill=text_color, align="left")
        y += getheight(font, line) + padding

    return image

def merge_background_audio(audio: ffmpeg, reddit_id: str):
    """Merge TTS audio with background audio."""
    background_audio_volume = settings.config["settings"]["background"]["background_audio_volume"]
    if background_audio_volume == 0:
        return audio
    
    try:
        # Set volume to config
        bg_audio = ffmpeg.input(f"assets/temp/{reddit_id}/background.mp3").filter(
            "volume",
            background_audio_volume,
        )
        # Merge audio and background_audio
        merged_audio = ffmpeg.filter([audio, bg_audio], "amix", duration="longest")
        return merged_audio
    except Exception as e:
        print(f"Error merging background audio: {e}")
        # Fall back to original audio if merging fails
        return audio

def make_final_video(
    number_of_clips: int,
    length: int,
    reddit_obj: dict,
    background_config: Dict[str, Tuple],
):
    """Create the final video by combining all components."""
    W: Final[int] = int(settings.config["settings"]["resolution_w"])
    H: Final[int] = int(settings.config["settings"]["resolution_h"])
    opacity = settings.config["settings"]["opacity"]
    reddit_id = re.sub(r"[^\w\s-]", "", reddit_obj["thread_id"])
    
    # Verify all required files exist
    verify_files_exist(
        reddit_id, 
        number_of_clips,
        settings.config["settings"]["storymode"]
    )

    print_step("Creating the final video 🎥")

    try:
        background_clip = ffmpeg.input(prepare_background(reddit_id, W=W, H=H))

        # Gather all audio clips
        audio_clips = []
        if number_of_clips == 0 and not settings.config["settings"]["storymode"]:
            print("No audio clips to gather. Please use a different TTS or post.")
            return

        # Handle audio clips based on mode
        if settings.config["settings"]["storymode"]:
            if settings.config["settings"]["storymodemethod"] == 0:
                audio_clips = [ffmpeg.input(f"assets/temp/{reddit_id}/mp3/title.mp3")]
                audio_clips.append(ffmpeg.input(f"assets/temp/{reddit_id}/mp3/postaudio.mp3"))
            else:
                audio_clips = [
                    ffmpeg.input(f"assets/temp/{reddit_id}/mp3/postaudio-{i}.mp3")
                    for i in track(range(number_of_clips + 1), "Collecting the audio files...")
                ]
                audio_clips.insert(0, ffmpeg.input(f"assets/temp/{reddit_id}/mp3/title.mp3"))
        else:
            audio_clips = [
                ffmpeg.input(f"assets/temp/{reddit_id}/mp3/{i}.mp3") 
                for i in range(number_of_clips)
            ]
            audio_clips.insert(0, ffmpeg.input(f"assets/temp/{reddit_id}/mp3/title.mp3"))

        # Concatenate audio clips
        audio_concat = ffmpeg.concat(*audio_clips, a=1, v=0)
        ffmpeg.output(
            audio_concat, 
            f"assets/temp/{reddit_id}/audio.mp3",
            **{"b:a": "192k"}
        ).overwrite_output().run(quiet=True)

        # Get audio durations
        audio_clips_durations = []
        for i in range(number_of_clips + 1):
            try:
                if settings.config["settings"]["storymode"]:
                    file_path = f"assets/temp/{reddit_id}/mp3/postaudio-{i}.mp3"
                else:
                    file_path = f"assets/temp/{reddit_id}/mp3/{i}.mp3"
                duration = float(ffmpeg.probe(file_path)["format"]["duration"])
                audio_clips_durations.append(duration)
            except Exception as e:
                print(f"Error getting duration for clip {i}: {e}")
                raise

        console.log(f"[bold green] Video Will Be: {length} Seconds Long")

        # Process audio
        audio = ffmpeg.input(f"assets/temp/{reddit_id}/audio.mp3")
        final_audio = merge_background_audio(audio, reddit_id)

        # Process images
        screenshot_width = int((W * 45) // 100)
        image_clips = []
        Path(f"assets/temp/{reddit_id}/png").mkdir(parents=True, exist_ok=True)

        # Create and save title image
        title_template = Image.open("assets/title_template.png")
        title = name_normalize(reddit_obj["thread_title"])
        title_img = create_fancy_thumbnail(title_template, title, "#000000", 5)
        title_img.save(f"assets/temp/{reddit_id}/png/title.png")
        
        image_clips.insert(
            0,
            ffmpeg.input(f"assets/temp/{reddit_id}/png/title.png")["v"].filter(
                "scale", screenshot_width, -1
            ),
        )

        current_time = 0
        if settings.config["settings"]["storymode"]:
            # Create a transparent image for story mode
            transparent_image = Image.new('RGBA', (screenshot_width, screenshot_width), (0, 0, 0, 0))
            transparent_image.save(f"assets/temp/{reddit_id}/png/transparent.png")

            if settings.config["settings"]["storymodemethod"] == 0:
                image_clips.insert(
                    1,
                    ffmpeg.input(f"assets/temp/{reddit_id}/png/story_content.png").filter(
                        "scale", screenshot_width, -1
                    ),
                )
                background_clip = background_clip.overlay(
                    image_clips[0],
                    enable=f"between(t,{current_time},{current_time + audio_clips_durations[0]})",
                    x="(main_w-overlay_w)/2",
                    y="(main_h-overlay_h)/2",
                )
                current_time += audio_clips_durations[0]
            else:
                for i in track(range(0, number_of_clips + 1), "Collecting the image files..."):
                    # Create a transparent image for each clip
                    transparent_image = Image.new('RGBA', (screenshot_width, screenshot_width), (0, 0, 0, 0))
                    transparent_image.save(f"assets/temp/{reddit_id}/png/trs{i}.png")

                    image_clips.append(
                        ffmpeg.input(f"assets/temp/{reddit_id}/png/trs{i}.png")["v"].filter(
                            "scale", screenshot_width, -1
                        )
                    )
                    background_clip = background_clip.overlay(
                        image_clips[i],
                        enable=f"between(t,{current_time},{current_time + audio_clips_durations[i]})",
                        x="(main_w-overlay_w)/2",
                        y="(main_h-overlay_h)/2",
                    )
                    current_time += audio_clips_durations[i]
        else:
            for i in range(0, number_of_clips + 1):
                try:
                    image_clips.append(
                        ffmpeg.input(f"assets/temp/{reddit_id}/png/comment_{i}.png")["v"].filter(
                            "scale", screenshot_width, -1
                        )
                    )
                    image_overlay = image_clips[i].filter("colorchannelmixer", aa=opacity)
                    background_clip = background_clip.overlay(
                        image_overlay,
                        enable=f"between(t,{current_time},{current_time + audio_clips_durations[i]})",
                        x="(main_w-overlay_w)/2",
                        y="(main_h-overlay_h)/2",
                    )
                    current_time += audio_clips_durations[i]
                except Exception as e:
                    print(f"Error processing image {i}: {e}")
                    raise

        # Process title and prepare output paths
        title = name_normalize(reddit_obj["thread_title"])
        filename = f"{title[:251]}"
        subreddit = settings.config["reddit"]["thread"]["subreddit"]

        # Create necessary directories
        for dir_path in [
            f"./results/{subreddit}",
            f"./results/{subreddit}/OnlyTTS",
            f"./results/{subreddit}/thumbnails"
        ]:
            if not exists(dir_path):
                print_substep(f"Creating directory: {dir_path}")
                os.makedirs(dir_path)

        # Create thumbnail if enabled
        if settings.config["settings"]["background"]["background_thumbnail"]:
            first_image = next(
                (file for file in os.listdir("assets/backgrounds") if file.endswith(".png")),
                None,
            )
            if first_image:
                thumbnail = Image.open(f"assets/backgrounds/{first_image}")
                width, height = thumbnail.size
                bg_config = settings.config["settings"]["background"]
                thumbnailSave = create_thumbnail(
                    thumbnail,
                    bg_config["background_thumbnail_font_family"],
                    bg_config["background_thumbnail_font_size"],
                    bg_config["background_thumbnail_font_color"],
                    width,
                    height,
                    reddit_obj["thread_title"],
                )
                thumbnailSave.save(f"./assets/temp/{reddit_id}/thumbnail.png")
                print_substep(f"Created thumbnail in assets/temp/{reddit_id}/thumbnail.png")
            else:
                print_substep("No png files found in assets/backgrounds", "red")

        # Add minimal watermark
        text = " "  # Removed background creator mention
        background_clip = ffmpeg.drawtext(
            background_clip,
            text=text,
            x=f"(w-text_w)",
            y=f"(h-text_h)",
            fontsize=5,
            fontcolor="White",
            fontfile=os.path.join("fonts", "Roboto-Regular.ttf"),
        )
        background_clip = background_clip.filter("scale", W, H)

        # Render the final video
        print_step("Rendering the video 🎥")
        pbar = tqdm(total=100, desc="Progress: ", bar_format="{l_bar}{bar}", unit=" %")

        def on_update_example(progress):
            status = round(progress * 100, 2)
            old_percentage = pbar.n
            pbar.update(status - old_percentage)

        # Process main video
        defaultPath = f"results/{subreddit}"
        with ProgressFfmpeg(length, on_update_example) as progress:
            path = defaultPath + f"/{filename}"
            path = path[:251] + ".mp4"  # Limit path length
            
            try:
                try_ffmpeg_output(
                    background_clip,
                    final_audio,
                    path,
                    progress.output_file.name
                )
            except ffmpeg.Error as e:
                print("Error during final video rendering:")
                print(e.stderr.decode("utf8") if e.stderr else "No error details available")
                raise

        # Process TTS-only version if enabled
        if settings.config["settings"]["background"]["enable_extra_audio"]:
            path = defaultPath + f"/OnlyTTS/{filename}"
            path = path[:251] + ".mp4"
            print_step("Rendering the Only TTS Video 🎥")
            
            with ProgressFfmpeg(length, on_update_example) as progress:
                try:
                    try_ffmpeg_output(
                        background_clip,
                        audio,
                        path,
                        progress.output_file.name
                    )
                except ffmpeg.Error as e:
                    print("Error during TTS-only video rendering:")
                    print(e.stderr.decode("utf8") if e.stderr else "No error details available")
                    raise

        pbar.close()

        # Save metadata and clean up
        save_data(subreddit, filename + ".mp4", title, reddit_id, background_config["video"][2])
        print_step("Removing temporary files 🗑")
        cleanups = cleanup(reddit_id)
        print_substep(f"Removed {cleanups} temporary files 🗑")
        print_step("Done! 🎉 The video is in the results folder 📁")
    except Exception as e:
        print(f"Error in video generation: {str(e)}")
        raise