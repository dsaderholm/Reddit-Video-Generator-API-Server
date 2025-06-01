import multiprocessing
import os
import re
import subprocess
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
    """Verify all required files exist before processing."""
    # Ensure base directories exist
    base_path = f"assets/temp/{reddit_id}"
    for subdir in ['mp3', 'png']:
        dir_path = os.path.join(base_path, subdir)
        os.makedirs(dir_path, exist_ok=True)
        
    # Define required paths
    required_files = []
    
    # Always required files
    required_files.append(f"assets/temp/{reddit_id}/background.mp4")
    
    # Story mode files
    if is_story_mode:
        if settings.config["settings"]["storymodemethod"] == 0:
            required_files.extend([
                f"assets/temp/{reddit_id}/mp3/title.mp3",
                f"assets/temp/{reddit_id}/mp3/postaudio.mp3"
            ])
        else:
            required_files.append(f"assets/temp/{reddit_id}/mp3/title.mp3")
            for i in range(number_of_clips + 1):
                required_files.append(f"assets/temp/{reddit_id}/mp3/postaudio-{i}.mp3")
    else:
        # Regular mode files
        required_files.append(f"assets/temp/{reddit_id}/mp3/title.mp3")
        for i in range(number_of_clips):
            required_files.append(f"assets/temp/{reddit_id}/mp3/{i}.mp3")
            required_files.append(f"assets/temp/{reddit_id}/png/comment_{i}.png")
    
    # Check file existence
    missing_files = []
    for file_path in required_files:
        if not os.path.exists(file_path):
            print(f"Missing file: {file_path}")
            missing_files.append(file_path)
            
    if missing_files:
        # Print directory contents for debugging
        print(f"\nContents of {base_path}:")
        for root, dirs, files in os.walk(base_path):
            print(f"\nDirectory: {root}")
            print("Files:", files)
            
        raise FileNotFoundError(f"Missing required files: {missing_files}")

class ProgressFfmpeg(threading.Thread):
    def __init__(self, vid_duration_seconds, progress_update_callback, progress_file_path=None):
        threading.Thread.__init__(self, name="ProgressFfmpeg")
        self.stop_event = threading.Event()
        if progress_file_path:
            self.progress_file_path = progress_file_path
            self.output_file = None
        else:
            self.output_file = tempfile.NamedTemporaryFile(mode="w+", delete=False)
            self.progress_file_path = self.output_file.name
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
            # Read from the progress file directly
            if os.path.exists(self.progress_file_path):
                with open(self.progress_file_path, 'r') as f:
                    lines = f.readlines()
            elif self.output_file:
                self.output_file.seek(0)
                lines = self.output_file.readlines()
            else:
                return None
            
            if lines:
                # Look for different progress indicators that ffmpeg outputs
                for line in reversed(lines):  # Start from the end for latest progress
                    line = line.strip()
                    if "out_time_ms=" in line:
                        out_time_ms_str = line.split("=")[1].strip()
                        if out_time_ms_str.isnumeric():
                            return float(out_time_ms_str) / 1000000.0
                    elif "out_time=" in line:
                        # Parse time format like "00:01:23.45" 
                        time_str = line.split("=")[1].strip()
                        try:
                            # Convert HH:MM:SS.mmm to seconds
                            parts = time_str.split(":")
                            if len(parts) == 3:
                                hours = float(parts[0])
                                minutes = float(parts[1])
                                seconds = float(parts[2])
                                return hours * 3600 + minutes * 60 + seconds
                        except ValueError:
                            continue
                    elif "time=" in line and "bitrate=" in line:
                        # Another common format: "time=00:01:23.45 bitrate=..."
                        try:
                            time_part = line.split("time=")[1].split()[0]
                            parts = time_part.split(":")
                            if len(parts) == 3:
                                hours = float(parts[0])
                                minutes = float(parts[1]) 
                                seconds = float(parts[2])
                                return hours * 3600 + minutes * 60 + seconds
                        except (ValueError, IndexError):
                            continue
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
    
    @property
    def output_file_name(self):
        """Get the progress file path for compatibility."""
        return self.progress_file_path

def try_ffmpeg_output(background_clip, final_audio, path: str, progress_file: str, reddit_id: str, max_retries: int = 3) -> bool:
    """Research-based Intel Arc hardware acceleration with proper drivers and syntax."""
    for attempt in range(max_retries):
        try:
            threads = min(16, max(1, multiprocessing.cpu_count() - 1))
            
            print(f"🚀 Attempting Intel Arc hardware encoding (attempt {attempt + 1})...")
            
            # Method 1: Intel Arc-specific QSV (requires proper drivers)
            try:
                print("🎯 Using Intel Arc QSV (requires updated drivers)...")
                
                cmd = [
                    "ffmpeg", "-y",
                    "-progress", progress_file,
                    "-threads", str(threads),
                    # QSV-specific initialization
                    "-init_hw_device", "qsv=hw",
                    "-filter_hw_device", "hw",
                    "-i", f"assets/temp/{reddit_id}/background_noaudio.mp4",
                    "-i", f"assets/temp/{reddit_id}/png/title.png",
                    "-i", f"assets/temp/{reddit_id}/audio.mp3",
                    "-filter_complex",
                    "[0:v]scale=1080:1920[bg];[1:v]scale=-1:1200:force_original_aspect_ratio=decrease[title];[bg][title]overlay=(main_w-overlay_w)/2:(main_h-overlay_h)/2:enable='between(t,0,8)',format=qsv,hwupload=extra_hw_frames=64[v]",
                    "-map", "[v]", "-map", "2:a",
                    "-c:v", "h264_qsv",
                    "-preset", "medium",
                    "-global_quality", "23",
                    "-c:a", "aac", "-b:a", "192k",
                    "-movflags", "+faststart",
                    path
                ]
                
                # Run with streaming output for progress tracking
                with open(progress_file, 'w') as prog_file:
                    result = subprocess.run(
                        cmd,
                        stdout=prog_file, 
                        stderr=subprocess.PIPE,
                        text=True,
                        timeout=600
                    )
                
                if result.returncode == 0:
                    print("✅ Intel Arc QSV encoding successful!")
                    return True
                else:
                    print(f"⚠️ QSV failed - likely driver issue (need intel-media-driver 22.5.2+)")
                    raise subprocess.CalledProcessError(result.returncode, cmd, result.stderr)
                    
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
                print(f"⚠️ QSV failed, trying VA-API with software overlay...")
                
                # Method 2: VA-API with software overlay (more compatible)
                try:
                    print("🔄 Using VA-API with software preprocessing...")
                    
                    cmd = [
                        "ffmpeg", "-y",
                        "-progress", progress_file,
                        "-threads", str(threads),
                        "-i", f"assets/temp/{reddit_id}/background_noaudio.mp4",
                        "-i", f"assets/temp/{reddit_id}/png/title.png",
                        "-i", f"assets/temp/{reddit_id}/audio.mp3",
                        "-filter_complex",
                        # Software overlay first, then hardware upload (Intel Arc compatible)
                        "[0:v]scale=1080:1920[bg];[1:v]scale=-1:1200:force_original_aspect_ratio=decrease[title];[bg][title]overlay=(main_w-overlay_w)/2:(main_h-overlay_h)/2:enable='between(t,0,8)',format=nv12,hwupload[v]",
                        "-map", "[v]", "-map", "2:a",
                        "-c:v", "h264_vaapi",
                        "-vaapi_device", "/dev/dri/renderD128",
                        "-qp", "23",
                        "-c:a", "aac", "-b:a", "192k",
                        "-movflags", "+faststart",
                        path
                    ]
                    
                    # Run with streaming output for progress tracking
                    with open(progress_file, 'w') as prog_file:
                        result = subprocess.run(
                            cmd,
                            stdout=prog_file,
                            stderr=subprocess.PIPE, 
                            text=True,
                            timeout=600
                        )
                    
                    if result.returncode == 0:
                        print("✅ Intel Arc VA-API encoding successful!")
                        return True
                    else:
                        print(f"⚠️ VA-API failed: {result.stderr[-200:] if result.stderr else 'Unknown error'}")
                        raise subprocess.CalledProcessError(result.returncode, cmd, result.stderr)
                        
                except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
                    print(f"⚠️ VA-API also failed, trying basic VA-API...")
                    
                    # Method 3: Basic VA-API without hardware upload in filter
                    try:
                        print("🔄 Trying basic VA-API encoding...")
                        
                        cmd = [
                            "ffmpeg", "-y",
                            "-progress", progress_file,
                            "-threads", str(threads),
                            "-hwaccel", "vaapi",
                            "-hwaccel_device", "/dev/dri/renderD128",
                            "-hwaccel_output_format", "vaapi",
                            "-i", f"assets/temp/{reddit_id}/background_noaudio.mp4",
                            "-i", f"assets/temp/{reddit_id}/png/title.png",
                            "-i", f"assets/temp/{reddit_id}/audio.mp3",
                            "-filter_complex",
                            "[0:v]scale_vaapi=1080:1920[bg];[1:v]format=yuv420p,hwupload,scale_vaapi=-1:486:force_original_aspect_ratio=decrease[title_scaled];[title_scaled]pad_vaapi=486:486:(ow-iw)/2:(oh-ih)/2[title];[bg][title]overlay_vaapi=x=(main_w-overlay_w)/2:y=(main_h-overlay_h)/2[v]",
                            "-map", "[v]", "-map", "2:a",
                            "-c:v", "h264_vaapi",
                            "-qp", "23",
                            "-c:a", "aac", "-b:a", "192k",
                            path
                        ]
                        
                        # Run with streaming output for progress tracking
                        with open(progress_file, 'w') as prog_file:
                            result = subprocess.run(
                                cmd,
                                stdout=prog_file,
                                stderr=subprocess.PIPE,
                                text=True, 
                                timeout=600
                            )
                        
                        if result.returncode == 0:
                            print("✅ Basic VA-API encoding successful!")
                            return True
                        else:
                            print(f"⚠️ Basic VA-API also failed")
                            raise subprocess.CalledProcessError(result.returncode, cmd, result.stderr)
                            
                    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
                        print(f"⚠️ All Intel Arc methods failed, falling back to software...")
                        raise e
            
        except Exception as e:
            print(f"❌ Intel Arc encoding attempt {attempt + 1} failed:")
            if hasattr(e, 'stderr') and e.stderr:
                error_msg = e.stderr if isinstance(e.stderr, str) else e.stderr.decode("utf8")
                print("Error:", error_msg)
                
                # Specific Intel Arc troubleshooting
                if "filter" in error_msg.lower() and "complex" in error_msg.lower():
                    print("💡 Filter conflict detected - this is why we're using raw commands")
                elif "qsv" in error_msg.lower() or "mfx" in error_msg.lower():
                    print("💡 QSV failed - Intel drivers may need updating")
                elif "vaapi" in error_msg.lower():
                    print("💡 VAAPI failed - trying software fallback")
                elif "device" in error_msg.lower():
                    print("💡 GPU device issue - check Docker device mapping")
            else:
                print(f"Error: {str(e)}")
            
            # Don't retry on the last attempt - just fail to software
            if attempt == max_retries - 1:
                print(f"❌ All Intel Arc attempts failed, using guaranteed software encoding...")
                break
            
            print(f"🔄 Retrying... ({attempt + 1}/{max_retries})")
            time.sleep(2)
    
    # Final fallback: Guaranteed to work software encoding
    print("🎯 Final attempt: Guaranteed software encoding...")
    try:
        threads = max(1, multiprocessing.cpu_count() - 1)
        
        cmd = [
            "ffmpeg", "-y",
            "-progress", progress_file,
            "-threads", str(threads),
            "-i", f"assets/temp/{reddit_id}/background_noaudio.mp4",
            "-i", f"assets/temp/{reddit_id}/png/title.png",
            "-i", f"assets/temp/{reddit_id}/audio.mp3",
            "-filter_complex",
            "[0:v]scale=1080:1920[bg];[1:v]scale=-1:1200:force_original_aspect_ratio=decrease[title];[bg][title]overlay=(main_w-overlay_w)/2:(main_h-overlay_h)/2:enable='between(t,0,8)'[v]",
            "-map", "[v]", "-map", "2:a",
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "23",
            "-tune", "fastdecode",
            "-b:v", "20M",
            "-c:a", "aac",
            "-b:a", "192k",
            "-movflags", "+faststart",
            "-pix_fmt", "yuv420p",
            path
        ]
        
        with open(progress_file, 'w') as prog_file:
            result = subprocess.run(
                cmd,
                stdout=prog_file,
                stderr=subprocess.PIPE,
                text=True,
                timeout=600
            )
        
        if result.returncode == 0:
            print("✅ Software encoding successful!")
            return True
        else:
            print(f"❌ Even software encoding failed:")
            if result.stderr:
                print("Final error:", result.stderr)
            raise subprocess.CalledProcessError(result.returncode, cmd, result.stderr)
            
    except Exception as final_error:
        print(f"❌ Software encoding exception: {final_error}")
        raise final_error

def name_normalize(name: str) -> str:
    """Normalize a filename to be safe for all operating systems."""
    # Remove null bytes and control characters
    name = re.sub(r'[\x00-\x1F\x7F]', '', name)
    name = re.sub(r'[\u200B-\u200F\uFEFF]', '', name)
    name = re.sub(r'\s+', ' ', name)
    name = name.strip()
    name = re.sub(r'[/\\\\]', '', name)
    
    # Handle common shorthand replacements
    name = re.sub(r'( [w,W]\s?\/\s?[o,O,0])', r' without', name)
    name = re.sub(r'( [w,W]\/)', r' with', name)
    name = re.sub(r'(\d+)\s?\/\s?(\d+)', r'\1 of \2', name)
    name = re.sub(r'(\w+)\s?\/\s?(\w+)', r'\1 or \2', name)
    
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
        if e.stderr:
            print("Error preparing background:", e.stderr.decode("utf8"))
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
        bg_audio = ffmpeg.input(f"assets/temp/{reddit_id}/background.mp3").filter(
            "volume",
            background_audio_volume,
        )
        merged_audio = ffmpeg.filter([audio, bg_audio], "amix", duration="longest")
        return merged_audio
    except Exception as e:
        print(f"Error merging background audio: {e}")
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
    
    # Ensure all base directories exist with proper permissions
    base_dirs = [
        "assets",
        "assets/temp",
        f"assets/temp/{reddit_id}",
        f"assets/temp/{reddit_id}/mp3",
        f"assets/temp/{reddit_id}/png",
        "results"
    ]
    
    for directory in base_dirs:
        try:
            os.makedirs(directory, exist_ok=True)
            # Ensure directory has proper permissions in Docker
            os.chmod(directory, 0o777)
        except Exception as e:
            print(f"Error creating directory {directory}: {str(e)}")
            raise
    
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
                os.chmod(dir_path, 0o777)  # Ensure Docker has write permissions

        # Create thumbnail if enabled
        if settings.config["settings"]["background"]["background_thumbnail"]:
            first_image = next(
                (file for file in os.listdir("assets/backgrounds") if file.endswith(".png")),
                None,
            )
            if first_image:
                try:
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
                except Exception as e:
                    print(f"Error creating thumbnail: {e}")
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
        path = defaultPath + f"/{filename}"
        path = path[:251] + ".mp4"  # Limit path length
        
        progress_file = f"assets/temp/{reddit_id}/progress.txt"
        with ProgressFfmpeg(length, on_update_example, progress_file) as progress:
            try:
                try_ffmpeg_output(
                background_clip,
                final_audio,
                path,
                progress_file,
                    reddit_id
                    )
            except ffmpeg.Error as e:
                print("Error during final video rendering:")
                if e.stderr:
                    print(e.stderr.decode("utf8"))
                raise

        # Process TTS-only version if enabled
        if settings.config["settings"]["background"]["enable_extra_audio"]:
            path = defaultPath + f"/OnlyTTS/{filename}"
            path = path[:251] + ".mp4"
            print_step("Rendering the Only TTS Video 🎥")
            
            progress_file_tts = f"assets/temp/{reddit_id}/progress_tts.txt"
            with ProgressFfmpeg(length, on_update_example, progress_file_tts) as progress:
                try:
                    try_ffmpeg_output(
                        background_clip,
                        audio,
                        path,
                        progress_file_tts,
                        reddit_id
                    )
                except ffmpeg.Error as e:
                    print("Error during TTS-only video rendering:")
                    if e.stderr:
                        print(e.stderr.decode("utf8"))
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