import os
import subprocess
import logging

# Set up logging for GPU initialization
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def initialize_intel_arc_gpu():
    """Simplified Intel Arc GPU initialization for FFmpeg hardware acceleration."""
    logger.info("🔍 Initializing Intel Arc GPU support for FFmpeg...")
    
    # Set Intel Arc optimization environment variables for FFmpeg
    intel_env_vars = {
        "LIBVA_DRIVER_NAME": "iHD",
        "LIBVA_DRIVERS_PATH": "/usr/lib/x86_64-linux-gnu/dri",
        # Intel Arc performance optimizations
        "INTEL_GPU_MIN_FREQ": "0",
        "INTEL_GPU_MAX_FREQ": "2100",
        # Intel Media Driver optimizations
        "INTEL_MEDIA_RUNTIME": "/usr/lib/x86_64-linux-gnu/dri",
        "MFX_IMPL_BASEDIR": "/usr/lib/x86_64-linux-gnu",
    }
    
    # Apply environment variables
    for key, value in intel_env_vars.items():
        os.environ[key] = value
        logger.debug(f"Set {key}={value}")
    
    try:
        # Verify hardware presence
        result = subprocess.run(['ls', '/dev/dri/'], capture_output=True, text=True)
        if 'renderD128' not in result.stdout:
            logger.error("❌ No Intel GPU render device found")
            return False
            
        # Verify VA-API functionality
        try:
            vainfo_result = subprocess.run(['vainfo', '--display', 'drm', '--device', '/dev/dri/renderD128'], 
                                         capture_output=True, text=True, timeout=10)
            if vainfo_result.returncode == 0:
                if 'H264' in vainfo_result.stdout:
                    logger.info("✅ VA-API H264 support confirmed")
                if 'HEVC' in vainfo_result.stdout:
                    logger.info("✅ VA-API HEVC support confirmed")
                if 'AV1' in vainfo_result.stdout:
                    logger.info("✅ VA-API AV1 support confirmed")
                logger.info("✅ Intel Arc GPU hardware acceleration ready for FFmpeg")
                return True
            else:
                logger.warning("⚠️ VA-API test failed, but GPU may still work with QSV")
                return True  # Continue anyway, QSV might work
        except subprocess.TimeoutExpired:
            logger.warning("⚠️ VA-API test timed out")
            return True  # Continue anyway
        except FileNotFoundError:
            logger.warning("⚠️ vainfo not found, install intel-gpu-tools for better diagnostics")
            return True  # Continue anyway
            
    except Exception as e:
        logger.error(f"❌ Error initializing Intel Arc GPU: {str(e)}")
        return False



def check_ffmpeg_hardware_support():
    """Verify FFmpeg hardware acceleration capabilities."""
    
    logger.info("🔍 Checking FFmpeg hardware acceleration support...")
    
    try:
        encoders = subprocess.run(['ffmpeg', '-encoders'], capture_output=True, text=True, timeout=10)
        decoders = subprocess.run(['ffmpeg', '-decoders'], capture_output=True, text=True, timeout=10)
        
        intel_encoders = [line for line in encoders.stdout.split('\n') 
                         if any(codec in line.lower() for codec in ['vaapi', 'qsv', 'intel'])]
        intel_decoders = [line for line in decoders.stdout.split('\n') 
                         if any(codec in line.lower() for codec in ['vaapi', 'qsv', 'intel'])]
        
        logger.info("✅ Intel Hardware Encoders:")
        for encoder in intel_encoders:
            if encoder.strip():
                logger.info(f"   {encoder.strip()}")
                
        logger.info("✅ Intel Hardware Decoders:")  
        for decoder in intel_decoders:
            if decoder.strip():
                logger.info(f"   {decoder.strip()}")
                
        return intel_encoders, intel_decoders
        
    except subprocess.TimeoutExpired:
        logger.error("❌ FFmpeg hardware check timed out")
        return [], []
    except FileNotFoundError:
        logger.error("❌ FFmpeg not found")
        return [], []
    except Exception as e:
        logger.error(f"❌ Error checking FFmpeg support: {e}")
        return [], []

# Legacy compatibility function
def initialize_intel_gpu():
    """Legacy function name for compatibility."""
    return initialize_intel_arc_gpu()

# Run hardware checks on import if this is the main module
if __name__ == "__main__":
    check_ffmpeg_hardware_support()
    initialize_intel_arc_gpu()
