from flask import Flask, send_file, jsonify
import subprocess
import os
import shutil
from pathlib import Path
import toml
import threading
import uuid
import time
import glob

app = Flask(__name__)

TEMP_DIR = "/app/assets/temp"
RESULTS_DIR = "/app/results"
CONFIG_PATH = "/app/config.toml"

def clean_temp():
    """Clean temporary directory"""
    if os.path.exists(TEMP_DIR):
        shutil.rmtree(TEMP_DIR)
        os.makedirs(TEMP_DIR)

def get_subreddit_path():
    """Get subreddit path from config"""
    with open(CONFIG_PATH, 'r') as f:
        config = toml.load(f)
    return config['reddit']['thread']['subreddit']

def run_video_generator():
    """Run the main.py script"""
    subprocess.run(["python3", "main.py"], check=True)

def find_latest_video():
    """Find the most recently created video file in any subreddit results folder"""
    subreddits = get_subreddit_path().split('+')
    latest_video = None
    latest_time = 0
    
    for subreddit in subreddits:
        subreddit_path = os.path.join(RESULTS_DIR, subreddit)
        if os.path.exists(subreddit_path):
            video_files = glob.glob(os.path.join(subreddit_path, '*.mp4'))
            for video in video_files:
                file_time = os.path.getmtime(video)
                if file_time > latest_time:
                    latest_time = file_time
                    latest_video = video
    
    return latest_video

@app.route('/generate', methods=['POST'])
def generate_video():
    try:
        # Clean temp directory
        clean_temp()
        
        # Generate unique ID for this run
        run_id = str(uuid.uuid4())
        
        # Run video generator in a separate thread
        thread = threading.Thread(target=run_video_generator)
        thread.start()
        thread.join()  # Wait for completion
        
        # Allow a small delay for file system operations to complete
        time.sleep(2)
        
        # Find the latest generated video
        video_path = find_latest_video()
        
        if not video_path:
            return jsonify({"error": "No video file found after generation"}), 500
            
        try:
            # Send the video file
            response = send_file(
                video_path,
                mimetype='video/mp4',
                as_attachment=True,
                download_name=f'reddit_video_{run_id}.mp4'
            )
            
            # Clean up after sending
            os.remove(video_path)
            clean_temp()
            
            return response
            
        except Exception as e:
            return jsonify({"error": f"Error sending video: {str(e)}"}), 500
        
    except subprocess.CalledProcessError as e:
        return jsonify({"error": f"Video generation failed: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy"}), 200

if __name__ == '__main__':
    # Ensure temp directory exists
    os.makedirs(TEMP_DIR, exist_ok=True)
    app.run(host='0.0.0.0', port=5000)
