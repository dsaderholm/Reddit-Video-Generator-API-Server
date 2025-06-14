import os
import shutil
from os.path import exists


def _listdir(d):  # listdir with full path
    return [os.path.join(d, f) for f in os.listdir(d)]


def cleanup(reddit_id) -> int:
    """Deletes all temporary assets in assets/temp

    Returns:
        int: How many files were deleted
    """
    # Try both possible directory paths
    directories = [
        f"assets/temp/{reddit_id}/",  # Current working directory
        f"../assets/temp/{reddit_id}/"  # Parent directory
    ]
    
    deleted_count = 0
    for directory in directories:
        if exists(directory):
            shutil.rmtree(directory)
            deleted_count += 1
            print(f"Cleaned up: {directory}")
    
    return deleted_count
