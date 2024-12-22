from flask import Flask, send_file, jsonify
import subprocess
import os
import shutil
from pathlib import Path
import toml
import threading
import uuid
import time

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
    return config['reddit']['thread']['subreddit'].replace('+', '')

def run_video_generator():
    """Run the main.py script"""
    subprocess.run(["python3", "main.py"], check=True)

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
        
        # Get the generated video
        subreddit_path = get_subreddit_path()
        results_dir = os.path.join(RESULTS_DIR, subreddit_path)
        
        if not os.path.exists(results_dir):
            return jsonify({"error": "Video generation failed"}), 500
            
        # Find the most recent video file
        video_files = [f for f in os.listdir(results_dir) if f.endswith('.mp4')]
        if not video_files:
            return jsonify({"error": "No video generated"}), 500
            
        latest_video = max(video_files, key=lambda f: os.path.getmtime(os.path.join(results_dir, f)))
        video_path = os.path.join(results_dir, latest_video)
        
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
        return jsonify({"error": str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)