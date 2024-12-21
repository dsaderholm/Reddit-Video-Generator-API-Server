import random
import subprocess
import json
from utils import settings

class GTTS:
    def __init__(self):
        self.max_chars = 5000
        self.voices = []
        self.tts_script = r"C:\Users\Home Server\Desktop\TTS\tts_handler.py"

    def run(self, text, filepath):
        try:
            result = subprocess.run(
                ["python", self.tts_script, text, filepath],
                capture_output=True,
                text=True
            )
            
            # Parse JSON output
            output = json.loads(result.stdout)
            if not output.get("success", False):
                raise Exception(output.get("message", "TTS failed"))
                
        except Exception as e:
            raise Exception(f"TTS generation failed: {str(e)}")

    def randomvoice(self):
        return random.choice(self.voices)