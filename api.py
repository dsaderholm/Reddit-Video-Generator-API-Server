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

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)

TEMP_DIR = "/app/assets/temp"
RESULTS_DIR = "/app/results"
CONFIG_PATH = "/app/config.toml"

def clean_temp():
    """Clean temporary directory"""
    if os.path.exists(TEMP_DIR):
        logger.debug(f"Cleaning temp directory: {TEMP_DIR}")
        shutil.rmtree(TEMP_DIR)
        os.makedirs(TEMP_DIR)
        logger.debug("Temp directory cleaned and recreated")

def get_subreddit_path():
    """Get subreddit path from config"""
    logger.debug("Reading config file")
    with open(CONFIG_PATH, 'r') as f:
        config = toml.load(f)
    subreddits = config['reddit']['thread']['subreddit']
    logger.debug(f"Found subreddits: {subreddits}")
    return subreddits

def run_video_generator():
    """Run the main.py script"""
    logger.debug("Starting video generator")
    process = subprocess.Popen(
        ["python3", "main.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True
    )
    stdout, stderr = process.communicate()
    logger.debug(f"Video generator output:\n{stdout}")
    if stderr:
        logger.error(f"Video generator errors:\n{stderr}")
    if process.returncode != 0:
        raise subprocess.CalledProcessError(process.returncode, ["python3", "main.py"])

def find_latest_video():
    """Find the most recently created video file in the results folder"""
    subreddits = get_subreddit_path()
    combined_path = os.path.join(RESULTS_DIR, subreddits)
    logger.debug(f"Looking for videos in combined path: {combined_path}")
    
    if os.path.exists(combined_path):
        logger.debug(f"Contents of combined path: {os.listdir(combined_path)}")
        video_files = [f for f in os.listdir(combined_path) 
                      if f.endswith('.mp4') and f != 'background.mp4']
        
        if video_files:
            latest_video = max(
                video_files,
                key=lambda x: os.path.getmtime(os.path.join(combined_path, x))
            )
            full_path = os.path.join(combined_path, latest_video)
            logger.debug(f"Found latest video: {full_path}")
            return full_path
    
    logger.debug("No video files found")
    return None

@app.route('/generate', methods=['POST'])
def generate_video():
    try:
        logger.debug("Starting video generation process")
        
        # Clean temp directory
        clean_temp()
        
        # Generate unique ID for this run
        run_id = str(uuid.uuid4())
        logger.debug(f"Generated run ID: {run_id}")
        
        # Run video generator
        logger.debug("Starting video generator thread")
        thread = threading.Thread(target=run_video_generator)
        thread.start()
        thread.join()
        logger.debug("Video generator thread completed")
        
        # Allow a small delay for file system operations to complete
        time.sleep(2)
        logger.debug("Waited for file system operations")
        
        # Find the latest generated video
        video_path = find_latest_video()
        
        if not video_path:
            logger.error("No video file found after generation")
            return jsonify({"error": "No video file found after generation"}), 500
            
        logger.debug(f"Found video at path: {video_path}")
            
        try:
            logger.debug("Attempting to send video file")
            # Send the video file
            response = send_file(
                video_path,
                mimetype='video/mp4',
                as_attachment=True,
                download_name=f'reddit_video_{run_id}.mp4'
            )
            
            # Clean up after sending
            logger.debug("Cleaning up video file and temp directory")
            os.remove(video_path)
            clean_temp()
            
            logger.debug("Successfully sent video file")
            return response
            
        except Exception as e:
            logger.error(f"Error sending video: {str(e)}", exc_info=True)
            return jsonify({"error": f"Error sending video: {str(e)}"}), 500
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Video generation failed: {str(e)}", exc_info=True)
        return jsonify({"error": f"Video generation failed: {str(e)}"}), 500
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy"}), 200

if __name__ == '__main__':
    # Ensure temp directory exists
    os.makedirs(TEMP_DIR, exist_ok=True)
    logger.debug("Starting Flask application")
    app.run(host='0.0.0.0', port=5000)