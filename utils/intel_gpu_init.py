import os
import torch

def initialize_intel_gpu():
    """Initialize Intel GPU support for PyTorch"""
    # Enable verbose logging for debugging GPU initialization
    os.environ["ONEAPI_DEVICE_SELECTOR"] = "level_zero:gpu"
    os.environ["INTEL_DEVICE_TYPE"] = "gpu"
    os.environ["USE_IPEX"] = "1"
    
    try:
        # Import Intel PyTorch Extension
        import intel_extension_for_pytorch as ipex
        
        # Check if Intel GPU is available
        if torch.xpu.is_available():
            print("Intel XPU (GPU) is available. Using Intel Arc A380.")
            # Set default device to Intel XPU
            torch.set_default_device('xpu')
            return True
        else:
            print("Intel XPU (GPU) is not available. Falling back to CPU.")
            return False
    except ImportError:
        print("Intel Extension for PyTorch not available. Falling back to CPU.")
        return False
    except Exception as e:
        print(f"Error initializing Intel GPU: {str(e)}")
        return False
