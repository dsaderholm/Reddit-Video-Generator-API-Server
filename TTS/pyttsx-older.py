import subprocess
import json
import os
import re

class pyttsx:
    def __init__(self):
        self.tts_path = r"C:\Users\Home Server\Desktop\TTS\tts_handler.py"
        self.max_chars = 5000
        self.python_path = r"C:\Users\Home Server\.pyenv\pyenv-win\versions\3.12.2\python.exe"
        # Default seeds (audio_seed text_seed seed)
        self.audio_seed = 79
        self.text_seed = 312
        self.seed = 649
        
        # Reddit shorthand mappings
        self.reddit_mappings = {
            'DM': 'Direct Message',
            'PM': 'Private Message',
            'AITA': 'am I the ass hole',
            'AITAH': 'am I the ass hole',
            'TIFU': 'today I fucked up',
            'TL;DR': 'too long, didn\'t read',
            'TLDR': 'too long, didn\'t read',
            'TL; DR': 'too long, didn\'t read',
            'ETA': 'edited to add',
            'FWIW': 'for what it\'s worth',
            'IMO': 'in my opinion',
            'IMHO': 'in my humble opinion',
            'AFAIK': 'as far as I know',
            'TIL': 'today I learned',
            'IIRC': 'if I remember correctly',
            'FTFY': 'fixed that for you',
            'IANAL': 'I am not a lawyer',
            'IME': 'in my experience',
            'IMO': 'in my opinion',
            'GF': 'girlfriend',
            'BF': 'boyfriend',
            'MIL': 'mother in law',
            'SIL': 'sister in law',
            'BIL': 'brother in law',
        }

    def _convert_age_gender(self, text):
        """Convert age/gender format (e.g., 24F, 25M) to written form"""
        def replace_match(match):
            age = match.group(1)
            gender = 'woman' if match.group(2).upper() == 'F' else 'man'
            return f"a {age}-year-old {gender}"
        
        return re.sub(r'(\d+)([MF])\b', replace_match, text, flags=re.IGNORECASE)

    def _preprocess_text(self, text):
        """Process Reddit shorthand and formatting"""
        # Handle age/gender formats first
        text = self._convert_age_gender(text)
        
        # Replace Reddit abbreviations
        for shorthand, full_text in self.reddit_mappings.items():
            # Use word boundaries to avoid partial matches
            text = re.sub(r'\b' + re.escape(shorthand) + r'\b', full_text, text, flags=re.IGNORECASE)
            
        return text

    def _ensure_paths(self):
        """Verify that all required paths exist"""
        for path in [self.tts_path, self.python_path]:
            if not os.path.exists(path):
                raise FileNotFoundError(f"Required path not found: {path}")

    def set_seeds(self, audio_seed=None, text_seed=None, seed=None):
        """Set custom seeds for voice generation"""
        if audio_seed is not None:
            self.audio_seed = audio_seed
        if text_seed is not None:
            self.text_seed = text_seed
        if seed is not None:
            self.seed = seed

    def run(self, text: str, filepath: str, random_voice=False):
        """Run the TTS system to generate audio"""
        self._ensure_paths()
        
        # Preprocess text before TTS generation
        processed_text = self._preprocess_text(text)
        
        try:
            print(f"Original filepath: {filepath}")
            print(f"Original working directory: {os.getcwd()}")
            abs_filepath = os.path.abspath(filepath)
            print(f"Absolute filepath: {abs_filepath}")
            
            current_dir = os.getcwd()
            os.chdir(os.path.dirname(self.tts_path))
            print(f"New working directory: {os.getcwd()}")
            
            env = os.environ.copy()
            env["PYTHONPATH"] = os.path.dirname(self.tts_path)
            
            command = [self.python_path, self.tts_path, processed_text, abs_filepath]
            
            if not random_voice:
                command.extend([
                    str(self.audio_seed),
                    str(self.text_seed),
                    str(self.seed)
                ])
            
            print(f"Running command: {' '.join(command)}")
            
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                env=env
            )
            
            os.chdir(current_dir)
            
            if result.stderr:
                try:
                    for line in result.stderr.splitlines():
                        try:
                            debug_info = json.loads(line)
                            if "debug" in debug_info:
                                print("TTS Debug:", debug_info["debug"])
                            elif "success" in debug_info and not debug_info["success"]:
                                print("TTS Error:", debug_info.get("message", "Unknown error"))
                                return False
                        except json.JSONDecodeError:
                            print("TTS Output:", line)
                except Exception as e:
                    print("Error processing TTS output:", str(e))
            
            exists = os.path.exists(abs_filepath)
            print(f"File exists at {abs_filepath}: {exists}")
            
            return exists
            
        except Exception as e:
            print(f"TTS Error: {str(e)}")
            return False

    def generate(self, text: str, filepath: str, random_voice=False):
        """Convenience method that validates input before running TTS"""
        if not text or not filepath:
            print("Error: Text and filepath are required")
            return False
            
        if len(text) > self.max_chars:
            print(f"Error: Text exceeds maximum length of {self.max_chars} characters")
            return False
            
        return self.run(text, filepath, random_voice)