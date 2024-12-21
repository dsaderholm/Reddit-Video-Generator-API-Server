from flask import Flask, send_file, jsonify
import os
import shutil
from subprocess import run
import toml
from pathlib import Path

app = Flask(__name__)

def get_subreddit_path():
    config = toml.load('/app/config.toml')
    return config['reddit']['thread']['subreddit'].replace('+', '')

def cleanup_temp():
    temp_dir = '/app/assets/temp'
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
        os.makedirs(temp_dir)

@app.route('/generate', methods=['POST'])
def generate_video():
    try:
        # Clean temp directory
        cleanup_temp()
        
        # Run the video generator
        result = run(['python3', 'main.py'], capture_output=True, text=True)
        
        if result.returncode != 0:
            return jsonify({
                'error': 'Video generation failed',
                'details': result.stderr
            }), 500

        # Get the subreddit path from config
        subreddit_path = get_subreddit_path()
        
        # Find the most recent video file
        results_dir = f'/app/results/{subreddit_path}'
        video_files = [f for f in os.listdir(results_dir) if f.endswith('.mp4')]
        if not video_files:
            return jsonify({'error': 'No video file generated'}), 500
            
        latest_video = max(video_files, key=lambda x: os.path.getctime(os.path.join(results_dir, x)))
        video_path = os.path.join(results_dir, latest_video)
        
        # Send the video file
        return send_file(video_path, mimetype='video/mp4')
        
    except Exception as e:
        return jsonify({
            'error': 'Server error',
            'details': str(e)
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
