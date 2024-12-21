import os
import re
import json
import requests
import subprocess
import tempfile

class pyttsx:
    def __init__(self, base_url="http://192.168.1.8:8888"):
        self.base_url = base_url
        self.max_chars = 5000
        self.pitch_factor = 0.9  # Fixed 10% pitch reduction
        
        # Default voice settings
        self.default_voice = {
            "speed": 1.0,
            "language": "EN",
            "speaker_id": "EN-BR"
        }
        
        # Reddit shorthand mappings
        self.reddit_mappings = {
            'DM': 'Direct Message',
            'PM': 'Private Message',
            'AITA': 'am I the ay hole',
            'AITAH': 'am I the ay hole',
            'TIFU': 'today I effed up',
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
            'GF': 'girl friend',
            'BF': 'boy friend',
            'MIL': 'mother in law',
            'FIL': 'father in law',
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

    def _convert_time_format(self, text):
        """Convert time formats (e.g., 5pm, 10AM) to phonetic form"""
        def replace_time(match):
            hour = match.group(1)
            meridiem = match.group(2).lower()
            return f"{hour} {' '.join(self.phonetic_letters[letter.upper()] for letter in meridiem)}"
        
        return re.sub(r'(\d+)\s*(am|pm|AM|PM)', replace_time, text)

    def _preprocess_text(self, text):
        """Process Reddit shorthand and formatting"""
        # Handle age/gender formats first
        text = self._convert_age_gender(text)
        
        # Convert time formats
        text = self._convert_time_format(text)
        
        # Replace Reddit abbreviations
        for shorthand, full_text in self.reddit_mappings.items():
            text = re.sub(r'\b' + re.escape(shorthand) + r'\b', full_text, text, flags=re.IGNORECASE)
        
        # Clean up any extra spaces
        text = ' '.join(text.split())
        
        return text

    def _adjust_audio_pitch(self, input_path, output_path):
        """Adjust the pitch of an audio file using ffmpeg"""
        try:
            cmd = [
                'ffmpeg',
                '-i', input_path,
                '-filter_complex', f'asetrate=44100*{self.pitch_factor},atempo={1/self.pitch_factor}',
                '-y',
                output_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                print(f"FFmpeg Error: {result.stderr}")
                return False
                
            return True
            
        except subprocess.SubprocessError as e:
            print(f"FFmpeg Process Error: {str(e)}")
            return False

    def _make_api_request(self, text, output_path):
        """Make the API request to generate TTS"""
        headers = {
            "Content-Type": "application/json"
        }
        
        payload = {
            "text": text,
            **self.default_voice
        }
        
        url = f"{self.base_url}/convert/tts"
        
        try:
            # Create a temporary file for the original audio
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                temp_path = temp_file.name
            
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            
            # Save the initial audio to temporary file
            with open(temp_path, 'wb') as f:
                f.write(response.content)
            
            # Ensure output directory exists
            output_dir = os.path.dirname(output_path)
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)
            
            # Adjust the pitch
            success = self._adjust_audio_pitch(temp_path, output_path)
            
            # Clean up temporary file
            os.unlink(temp_path)
            
            return success
            
        except requests.exceptions.RequestException as e:
            print(f"API Error: {str(e)}")
            return False
        except IOError as e:
            print(f"File Error: {str(e)}")
            return False

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
            # Preprocess text before TTS generation
            processed_text = self._preprocess_text(text)
            
            print(f"Original filepath: {filepath}")
            abs_filepath = os.path.abspath(filepath)
            print(f"Absolute filepath: {abs_filepath}")
            
            # Make the API request with pitch adjustment
            success = self._make_api_request(processed_text, abs_filepath)
            
            if success:
                exists = os.path.exists(abs_filepath)
                print(f"File exists at {abs_filepath}: {exists}")
                return exists
            return False
            
        except Exception as e:
            print(f"TTS Error: {str(e)}")
            return False

if __name__ == "__main__":
    # Example usage
    tts = pyttsx()
    text = "AITA (24F) for telling my BF (26M) that he needs to stop playing video games? Meeting at 5pm in Room A."
    tts.generate(text, "output.wav")