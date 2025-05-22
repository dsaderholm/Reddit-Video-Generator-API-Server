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

# Import Intel GPU initialization
from utils.intel_gpu_init import initialize_intel_arc_gpu, check_ffmpeg_hardware_support

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
    """Run the main.py script with real-time logging and a 20-minute timeout"""
    logger.debug("Starting video generator")
    try:
        # Use Popen to enable real-time logging
        process = subprocess.Popen(
            ["python3", "main.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            bufsize=1  # Line buffered
        )
        
        # Function to log output in real-time
        def log_output(pipe, log_func):
            for line in iter(pipe.readline, ''):
                log_func(line.rstrip())
            pipe.close()
        
        # Create threads to read stdout and stderr
        stdout_thread = threading.Thread(
            target=log_output, 
            args=(process.stdout, logger.info)
        )
        stderr_thread = threading.Thread(
            target=log_output, 
            args=(process.stderr, logger.error)
        )
        
        # Start logging threads
        stdout_thread.start()
        stderr_thread.start()
        
        # Wait for the process with timeout
        start_time = time.time()
        while process.poll() is None:
            elapsed_time = time.time() - start_time
            if elapsed_time >= VIDEO_TIMEOUT:
                process.kill()
                raise subprocess.TimeoutExpired(["python3", "main.py"], VIDEO_TIMEOUT)
            time.sleep(1)  # Check process status every second
        
        # Wait for logging threads to complete
        stdout_thread.join()
        stderr_thread.join()
        
        # Check return code
        if process.returncode != 0:
            raise subprocess.CalledProcessError(process.returncode, ["python3", "main.py"])
            
    except subprocess.TimeoutExpired:
        logger.error(f"Video generation timed out after {VIDEO_TIMEOUT//60} minutes")
        process.kill()
        raise Exception(f"Video generation timed out after {VIDEO_TIMEOUT//60} minutes")
    except Exception as e:
        logger.error(f"Error in video generation: {str(e)}")
        raise

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
    # Initialize Intel Arc GPU on startup
    logger.info("🚀 Starting Reddit Video Generator API with Intel Arc GPU support")
    
    # Initialize Intel Arc GPU
    gpu_initialized = initialize_intel_arc_gpu()
    if gpu_initialized:
        logger.info("✅ Intel Arc GPU initialized successfully")
    else:
        logger.warning("⚠️ Intel Arc GPU not available, using CPU fallback")
    
    # Check FFmpeg hardware acceleration support
    check_ffmpeg_hardware_support()
    
    # Ensure temp directory exists
    os.makedirs(TEMP_DIR, exist_ok=True)
    logger.info("🌐 Starting Flask application on 0.0.0.0:5000")
    app.run(host='0.0.0.0', port=5000)