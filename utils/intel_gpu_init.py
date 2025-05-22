import os
import torch
import subprocess
import logging

# Set up logging for GPU initialization
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def initialize_intel_arc_gpu():
    """Enhanced Intel Arc GPU initialization with comprehensive checks."""
    logger.info("🔍 Initializing Intel Arc GPU support...")
    
    # Set Intel Arc optimization environment variables
    intel_env_vars = {
        "ONEAPI_DEVICE_SELECTOR": "level_zero:gpu",
        "INTEL_DEVICE_TYPE": "gpu", 
        "USE_IPEX": "1",
        "LIBVA_DRIVER_NAME": "iHD",
        "LIBVA_DRIVERS_PATH": "/usr/lib/x86_64-linux-gnu/dri",
        # Intel Arc performance optimizations
        "INTEL_GPU_MIN_FREQ": "0",
        "INTEL_GPU_MAX_FREQ": "2100",
        "ZE_AFFINITY_MASK": "0",  # Use first GPU if multiple present
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
            else:
                logger.warning("⚠️ VA-API test failed, but continuing...")
        except subprocess.TimeoutExpired:
            logger.warning("⚠️ VA-API test timed out")
        except FileNotFoundError:
            logger.warning("⚠️ vainfo not found, install intel-gpu-tools")
            
        # Test Intel Extension for PyTorch
        try:
            import intel_extension_for_pytorch as ipex
            logger.info(f"📦 IPEX version: {ipex.__version__}")
            
            # Check Intel XPU availability
            if torch.xpu.is_available():
                device_count = torch.xpu.device_count()
                logger.info(f"🎮 Intel XPU devices available: {device_count}")
                
                for i in range(device_count):
                    device_props = torch.xpu.get_device_properties(i)
                    logger.info(f"   Device {i}: {device_props.name}")
                    logger.info(f"   Total Memory: {device_props.total_memory // (1024**2)} MB")
                    logger.info(f"   GPU EU Count: {device_props.gpu_eu_count}")
                    
                    # Test tensor operations
                    try:
                        test_tensor = torch.randn(100, 100).to(f'xpu:{i}')
                        result = torch.mm(test_tensor, test_tensor.t())
                        logger.info(f"✅ XPU {i} tensor operations working")
                    except Exception as e:
                        logger.warning(f"⚠️ XPU {i} tensor test failed: {e}")
                
                # Set default device to first XPU
                torch.xpu.set_device(0)
                logger.info(f"🎯 Default XPU device set to: xpu:0")
                return True
            else:
                logger.warning("❌ Intel XPU not available - PyTorch extension installed but no XPU detected")
                return False
                
        except ImportError as e:
            logger.error(f"❌ Intel Extension for PyTorch not available: {e}")
            logger.info("💡 Install with: pip install intel-extension-for-pytorch==2.3.110+xpu --extra-index-url https://pytorch-extension.intel.com/release-whl/stable/xpu/us/")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error initializing Intel Arc GPU: {str(e)}")
        return False

def get_optimal_device():
    """Get the optimal device for computations."""
    if initialize_intel_arc_gpu():
        return 'xpu:0'
    elif torch.cuda.is_available():
        return 'cuda:0'
    else:
        return 'cpu'

def move_model_to_device(model, device=None):
    """Move model to optimal device with Intel Arc optimizations."""
    if device is None:
        device = get_optimal_device()
        
    model = model.to(device)
    
    # Apply Intel Arc optimizations if using XPU
    if device.startswith('xpu'):
        try:
            import intel_extension_for_pytorch as ipex
            # Optimize model for Intel Arc
            model = ipex.optimize(model, dtype=torch.float16)
            logger.info(f"✅ Model optimized for Intel Arc GPU: {device}")
        except Exception as e:
            logger.warning(f"⚠️ Intel Arc optimization failed: {e}")
            
    return model, device

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
