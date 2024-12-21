import os
import re
from pathlib import Path
from typing import Tuple

import numpy as np
import translators
from moviepy.audio.AudioClip import AudioClip
from moviepy.audio.fx.volumex import volumex
from moviepy.editor import AudioFileClip
from rich.progress import track

from utils import settings
from utils.console import print_step, print_substep
from utils.voice import sanitize_text

DEFAULT_MAX_LENGTH: int = (
    70  # Video length variable, edit this on your own risk. It should work, but it's not supported
)


class TTSEngine:
    """Calls the given TTS engine to reduce code duplication and allow multiple TTS engines.

    Args:
        tts_module            : The TTS module. Your module should handle the TTS itself and saving to the given path under the run method.
        reddit_object         : The reddit object that contains the posts to read.
        path (Optional)       : The unix style path to save the mp3 files to. This must not have leading or trailing slashes.
        max_length (Optional) : The maximum length of the mp3 files in total.

    Notes:
        tts_module must take the arguments text and filepath.
    """

    def __init__(
        self,
        tts_module,
        reddit_object: dict,
        path: str = "assets/temp/",
        max_length: int = DEFAULT_MAX_LENGTH,
        last_clip_length: int = 0,
    ):
        self.tts_module = tts_module()
        self.reddit_object = reddit_object

        self.redditid = re.sub(r"[^\w\s-]", "", reddit_object["thread_id"])
        self.path = path + self.redditid + "/mp3"
        self.max_length = max_length
        self.length = 0
        self.last_clip_length = last_clip_length

    def add_periods(
        self,
    ):  # adds periods to the end of paragraphs (where people often forget to put them) so tts doesn't blend sentences
        for comment in self.reddit_object["comments"]:
            # remove links
            regex_urls = r"((http|https)\:\/\/)?[a-zA-Z0-9\.\/\?\:@\-_=#]+\.([a-zA-Z]){2,6}([a-zA-Z0-9\.\&\/\?\:@\-_=#])*"
            comment["comment_body"] = re.sub(regex_urls, " ", comment["comment_body"])
            comment["comment_body"] = comment["comment_body"].replace("\n", ". ")
            comment["comment_body"] = re.sub(r"\bAI\b", "A.I", comment["comment_body"])
            comment["comment_body"] = re.sub(r"\bAGI\b", "A.G.I", comment["comment_body"])
            if comment["comment_body"][-1] != ".":
                comment["comment_body"] += "."
            comment["comment_body"] = comment["comment_body"].replace(". . .", ".")
            comment["comment_body"] = comment["comment_body"].replace(".. . ", ".")
            comment["comment_body"] = comment["comment_body"].replace(". . ", ".")
            comment["comment_body"] = re.sub(r'\."\.', '".', comment["comment_body"])

    def run(self) -> Tuple[int, int]:
        Path(self.path).mkdir(parents=True, exist_ok=True)
        print_step("Saving Text to MP3 files...")

        self.add_periods()
        self.call_tts("title", process_text(self.reddit_object["thread_title"]))
        # processed_text = ##self.reddit_object["thread_post"] != ""
        idx = 0

        if settings.config["settings"]["storymode"]:
            if settings.config["settings"]["storymodemethod"] == 0:
                if len(self.reddit_object["thread_post"]) > self.tts_module.max_chars:
                    self.split_post(self.reddit_object["thread_post"], "postaudio")
                else:
                    self.call_tts("postaudio", process_text(self.reddit_object["thread_post"]))
            elif settings.config["settings"]["storymodemethod"] == 1:
                for idx, text in track(enumerate(self.reddit_object["thread_post"])):
                    self.call_tts(f"postaudio-{idx}", process_text(text))

        else:
            for idx, comment in track(enumerate(self.reddit_object["comments"]), "Saving..."):
                # ! Stop creating mp3 files if the length is greater than max length.
                if self.length > self.max_length and idx > 1:
                    self.length -= self.last_clip_length
                    idx -= 1
                    break
                if (
                    len(comment["comment_body"]) > self.tts_module.max_chars
                ):  # Split the comment if it is too long
                    self.split_post(comment["comment_body"], idx)  # Split the comment
                else:  # If the comment is not too long, just call the tts engine
                    self.call_tts(f"{idx}", process_text(comment["comment_body"]))

        print_substep("Saved Text to MP3 files successfully.", style="bold green")
        return self.length, idx

   
    def split_post(self, text: str, idx):
        split_files = []
        
        # Split text into smaller chunks
        split_text = []
        current_chunk = ""
        char_count = 0
        
        # Define splitting points
        split_chars = ['.', ',', '!', '?', ':', ';', '\n']
        max_chunk_size = 45

        for char in text:
            current_chunk += char
            char_count += 1
            
            # Check for split conditions
            if char in split_chars or char_count >= max_chunk_size:
                # If chunk is not empty and not just whitespace
                if current_chunk.strip():
                    split_text.append(current_chunk.strip())
                    print(f"Split chunk: '{current_chunk.strip()}' (length: {len(current_chunk.strip())})")
                current_chunk = ""
                char_count = 0
            
            # Force split if max size is reached without finding a split char
            if char_count == max_chunk_size:
                if current_chunk.strip():
                    split_text.append(current_chunk.strip())
                    print(f"Forced split: '{current_chunk.strip()}' (length: {len(current_chunk.strip())})")
                current_chunk = ""
                char_count = 0

        # Add any remaining text
        if current_chunk.strip():
            split_text.append(current_chunk.strip())
            print(f"Final chunk: '{current_chunk.strip()}' (length: {len(current_chunk.strip())})")

        print(f"Total chunks: {len(split_text)}")

        self.create_silence_mp3()

        idy = None
        for idy, text_cut in enumerate(split_text):
            newtext = process_text(text_cut)
            
            if not newtext or newtext.isspace():
                print(f"Chunk {idy} was blank after processing")
                continue
            else:
                print(f"Processing chunk {idy}: '{newtext}' (length: {len(newtext)})")
                self.call_tts(f"{idx}-{idy}.part", newtext)
                with open(f"{self.path}/list.txt", "a") as f:
                    f.write(f"file '{idx}-{idy}.part.mp3'\n")
                    f.write("file 'silence.mp3'\n")
                split_files.append(str(f"{self.path}/{idx}-{idy}.part.mp3"))

        # Combine all parts into a single MP3
        os.system(
            f"ffmpeg -f concat -y -hide_banner -loglevel panic -safe 0 "
            f"-i {self.path}/list.txt "
            f"-c copy {self.path}/{idx}.mp3"
        )

        # Clean up temporary files
        try:
            for file in split_files:
                os.unlink(file)
            os.unlink(f"{self.path}/list.txt")
        except FileNotFoundError as e:
            print(f"File not found: {e.filename}")
        except OSError as e:
            print(f"OSError: {e}")

        print(f"Finished processing {len(split_files)} audio chunks")


    def call_tts(self, filename: str, text: str):
        self.tts_module.run(
            text,
            filepath=f"{self.path}/{filename}.mp3",
            random_voice=settings.config["settings"]["tts"]["random_voice"],
        )
        # try:
        #     self.length += MP3(f"{self.path}/{filename}.mp3").info.length
        # except (MutagenError, HeaderNotFoundError):
        #     self.length += sox.file_info.duration(f"{self.path}/{filename}.mp3")
        try:
            clip = AudioFileClip(f"{self.path}/{filename}.mp3")
            self.last_clip_length = clip.duration
            self.length += clip.duration
            clip.close()
        except:
            self.length = 0

    def create_silence_mp3(self):
        silence_duration = settings.config["settings"]["tts"]["silence_duration"]
        silence = AudioClip(
            make_frame=lambda t: np.sin(440 * 2 * np.pi * t),
            duration=silence_duration,
            fps=44100,
        )
        silence = volumex(silence, 0)
        silence.write_audiofile(f"{self.path}/silence.mp3", fps=44100, verbose=False, logger=None)


def process_text(text: str, clean: bool = True):
    lang = settings.config["reddit"]["thread"]["post_lang"]
    new_text = sanitize_text(text) if clean else text
    if lang:
        print_substep("Translating Text...")
        translated_text = translators.translate_text(text, translator="google", to_language=lang)
        new_text = sanitize_text(translated_text)
    return new_text
