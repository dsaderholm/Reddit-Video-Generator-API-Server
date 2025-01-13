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
import logging
import re

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)

TEMP_DIR = "/app/assets/temp"
RESULTS_DIR = "/app/results"
CONFIG_PATH = "/app/config.toml"
VIDEO_TIMEOUT = 1200  # 20 minute timeout

def clean_temp():
    """Clean temporary directory"""
    if os.path.exists(TEMP_DIR):
        try:
            logger.debug(f"Cleaning temp directory: {TEMP_DIR}")
            shutil.rmtree(TEMP_DIR)
            os.makedirs(TEMP_DIR)
            logger.debug("Temp directory cleaned and recreated")
        except Exception as e:
            logger.error(f"Error cleaning temp directory: {str(e)}")
            raise

def get_subreddit_path():
    """Get subreddit path from config"""
    try:
        logger.debug("Reading config file")
        if not os.path.exists(CONFIG_PATH):
            raise FileNotFoundError(f"Config file not found at {CONFIG_PATH}")
        
        with open(CONFIG_PATH, 'r') as f:
            config = toml.load(f)
        
        subreddits = config.get('reddit', {}).get('thread', {}).get('subreddit')
        if not subreddits:
            raise ValueError("No subreddits found in config file")
            
        logger.debug(f"Found subreddits: {subreddits}")
        return subreddits
    except Exception as e:
        logger.error(f"Error reading config: {str(e)}")
        raise

def run_video_generator():
    """Run the main.py script with a 20-minute timeout"""
    logger.debug("Starting video generator")
    try:
        process = subprocess.run(
            ["python3", "main.py"],
            capture_output=True, 
            text=True,
            timeout=VIDEO_TIMEOUT
        )
        
        logger.debug(f"Video generator output:\n{process.stdout}")
        if process.stderr:
            logger.error(f"Video generator errors:\n{process.stderr}")
        
        if process.returncode != 0:
            raise subprocess.CalledProcessError(process.returncode, ["python3", "main.py"], process.stdout, process.stderr)
            
    except subprocess.TimeoutExpired:
        logger.error(f"Video generation timed out after {VIDEO_TIMEOUT//60} minutes")
        raise Exception(f"Video generation timed out after {VIDEO_TIMEOUT//60} minutes")

def find_latest_video():
    """Find the most recently created video file in the results folder"""
    try:
        subreddits = get_subreddit_path()
        combined_path = os.path.join(RESULTS_DIR, subreddits)
        logger.debug(f"Looking for videos in combined path: {combined_path}")
        
        if not os.path.exists(combined_path):
            logger.error(f"Results directory not found: {combined_path}")
            return None
            
        logger.debug(f"Contents of combined path: {os.listdir(combined_path)}")
        video_files = [f for f in os.listdir(combined_path) 
                      if f.endswith('.mp4') and f != 'background.mp4']
        
        if not video_files:
            logger.debug("No video files found")
            return None
            
        latest_video = max(
            video_files,
            key=lambda x: os.path.getmtime(os.path.join(combined_path, x))
        )
        full_path = os.path.join(combined_path, latest_video)
        logger.debug(f"Found latest video: {full_path}")
        return full_path
    except Exception as e:
        logger.error(f"Error finding latest video: {str(e)}")
        return None

@app.route('/generate', methods=['POST'])
def generate_video():
    try:
        logger.debug("Starting video generation process")
        clean_temp()
        run_id = str(uuid.uuid4())
        
        thread = threading.Thread(target=run_video_generator)
        thread.start()
        thread.join()
        
        # Allow some time for file system operations to complete
        time.sleep(2)
        video_path = find_latest_video()
        
        if not video_path:
            logger.error("No video file found after generation")
            return jsonify({"error": "No video file found after generation"}), 500
            
        if not os.path.exists(video_path):
            logger.error(f"Video file not found at path: {video_path}")
            return jsonify({"error": "Video file not found"}), 500
            
        try:
            response = send_file(
                video_path,
                mimetype='video/mp4',
                as_attachment=True,
                download_name=os.path.basename(video_path)
            )
            
            # Clean up after successful send
            try:
                os.remove(video_path)
                clean_temp()
            except Exception as e:
                logger.warning(f"Cleanup error (non-fatal): {str(e)}")
            
            return response
            
        except Exception as e:
            logger.error(f"Error sending video: {str(e)}", exc_info=True)
            return jsonify({"error": f"Error sending video: {str(e)}"}), 500
        
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        "status": "healthy",
        "temp_dir_exists": os.path.exists(TEMP_DIR),
        "results_dir_exists": os.path.exists(RESULTS_DIR),
        "config_exists": os.path.exists(CONFIG_PATH)
    }), 200

if __name__ == '__main__':
    # Ensure temp directory exists
    os.makedirs(TEMP_DIR, exist_ok=True)
    logger.debug("Starting Flask application")
    app.run(host='0.0.0.0', port=5000)