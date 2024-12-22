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

# Load config to get subreddit folder name
def get_results_folder():
    config = toml.load('config.toml')
    return config['reddit']['thread']['subreddit']

def cleanup_temp():
    temp_dir = Path('assets/temp')
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
        temp_dir.mkdir(exist_ok=True)

@app.route('/generate', methods=['POST'])
def generate_video():
    # Create a unique ID for this generation
    generation_id = str(uuid.uuid4())
    
    # Clean up temp directory
    cleanup_temp()
    
    # Start the video generation in a separate thread
    def generate():
        try:
            subprocess.run(['python3', 'main.py'], check=True)
            
            # Find the generated video
            results_dir = Path('results') / get_results_folder()
            video_files = list(results_dir.glob('*.mp4'))
            
            if not video_files:
                return
                
            # Move the latest video to a temporary location with the generation ID
            latest_video = max(video_files, key=lambda x: x.stat().st_mtime)
            new_path = Path('assets/temp') / f'{generation_id}.mp4'
            shutil.move(str(latest_video), str(new_path))
            
            # Clean up the results directory
            if results_dir.exists():
                shutil.rmtree(results_dir)
                
        except Exception as e:
            print(f"Error generating video: {e}")

    thread = threading.Thread(target=generate)
    thread.start()
    
    # Return the generation ID immediately
    return jsonify({
        'status': 'processing',
        'generation_id': generation_id,
        'message': 'Video generation started. Use /status/<generation_id> to check status and /video/<generation_id> to download when ready.'
    })

@app.route('/status/<generation_id>', methods=['GET'])
def check_status(generation_id):
    video_path = Path('assets/temp') / f'{generation_id}.mp4'
    
    if video_path.exists():
        return jsonify({
            'status': 'complete',
            'message': 'Video is ready for download'
        })
    else:
        return jsonify({
            'status': 'processing',
            'message': 'Video is still being generated'
        })

@app.route('/video/<generation_id>', methods=['GET'])
def get_video(generation_id):
    video_path = Path('assets/temp') / f'{generation_id}.mp4'
    
    if video_path.exists():
        return send_file(str(video_path), mimetype='video/mp4')
    else:
        return jsonify({
            'status': 'error',
            'message': 'Video not found or still processing'
        }), 404

if __name__ == '__main__':
    # Ensure temp directory exists
    Path('assets/temp').mkdir(parents=True, exist_ok=True)
    
    # Clean up temp directory on startup
    cleanup_temp()
    
    app.run(host='0.0.0.0', port=5000)
