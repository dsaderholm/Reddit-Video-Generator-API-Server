import os
import re
import json
import subprocess

class pyttsx:
    def __init__(self):
        self.tts_path = r"C:\Users\Home Server\Desktop\New TTS\tts_handler.py"
        self.max_chars = 5000
        self.python_path = r"C:\Users\Home Server\.pyenv\pyenv-win\versions\3.12.2\python.exe"
        
        # Default voice description
        self.default_voice = """Jon speaks slightly animatedly and slightly fast in delivery, with a very close recording that has no background noise."""
        
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
            'GF': 'girl friend',
            'BF': 'boy friend',
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

    def run(self, text, filepath, random_voice=False):
        """Maintained for backward compatibility"""
        return self.generate(text, filepath, random_voice)

    def generate(self, text, filepath, random_voice=False):
        """Generate TTS audio from Reddit text"""
        if not text or not filepath:
            print("Error: Text and filepath are required")
            return False
            
        if len(text) > self.max_chars:
            print(f"Error: Text exceeds maximum length of {self.max_chars} characters")
            return False
        
        try:
            self._ensure_paths()
            
            # Preprocess text before TTS generation
            processed_text = self._preprocess_text(text)
            
            print(f"Original filepath: {filepath}")
            abs_filepath = os.path.abspath(filepath)
            print(f"Absolute filepath: {abs_filepath}")
            
            env = os.environ.copy()
            env["PYTHONPATH"] = os.path.dirname(self.tts_path)
            
            # Build command
            command = [
                self.python_path,
                self.tts_path,
                processed_text,
                abs_filepath
            ]
            
            # Add voice description if not random
            if not random_voice:
                command.append(self.default_voice)
            
            print(f"Running command: {' '.join(command)}")
            
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                env=env
            )
            
            if result.stderr:
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
            
            exists = os.path.exists(abs_filepath)
            print(f"File exists at {abs_filepath}: {exists}")
            
            return exists
            
        except Exception as e:
            print(f"TTS Error: {str(e)}")
            return False

if __name__ == "__main__":
    # Example usage
    tts = pyttsx()
    text = "AITA (24F) for telling my BF (26M) that he needs to stop playing video games?"
    tts.generate(text, "output.wav")