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
    result = subprocess.run(["python3", "main.py"], 
                          check=True,
                          capture_output=True,
                          text=True)
    logger.debug(f"Video generator stdout: {result.stdout}")
    logger.debug(f"Video generator stderr: {result.stderr}")

def find_latest_video():
    """Find the most recently created video file in any subreddit results folder"""
    subreddits = get_subreddit_path().split('+')
    latest_video = None
    latest_time = 0
    
    logger.debug(f"Searching for videos in subreddits: {subreddits}")
    
    # First, log all results directories
    logger.debug(f"Contents of results directory {RESULTS_DIR}:")
    if os.path.exists(RESULTS_DIR):
        logger.debug(str(os.listdir(RESULTS_DIR)))
    else:
        logger.debug("Results directory does not exist!")
    
    for subreddit in subreddits:
        subreddit_path = os.path.join(RESULTS_DIR, subreddit)
        logger.debug(f"Checking subreddit path: {subreddit_path}")
        
        if os.path.exists(subreddit_path):
            video_files = glob.glob(os.path.join(subreddit_path, '*.mp4'))
            logger.debug(f"Found video files in {subreddit}: {video_files}")
            
            for video in video_files:
                file_time = os.path.getmtime(video)
                logger.debug(f"Video file: {video}, modified time: {file_time}")
                if file_time > latest_time:
                    latest_time = file_time
                    latest_video = video
    
    logger.debug(f"Latest video found: {latest_video}")
    return latest_video

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