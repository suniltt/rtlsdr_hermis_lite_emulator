"""
RTL-SDR Interface Module

This module provides a high-level interface to the RTL-SDR dongle,
handling device initialization, configuration, and IQ sample acquisition.

Author: RTL-Hermes Emulator Project
License: GPL-3.0
"""

import logging
from typing import Optional, Tuple, Generator
import numpy as np

try:
    from rtlsdr import RtlSdr
    RTLSDR_AVAILABLE = True
except ImportError:
    RTLSDR_AVAILABLE = False
    logging.warning("pyrtlsdr not installed. RTL-SDR functionality disabled.")

logger = logging.getLogger(__name__)


class RtlsdrInterface:
    """
    Interface class for RTL-SDR hardware operations.
    
    This class wraps the pyrtlsdr library to provide a clean API for:
    - Device detection and initialization
    - Configuration of sample rate, frequency, and gain
    - Streaming IQ samples
    - Error handling and device recovery
    
    Attributes:
        device (RtlSdr): The underlying RTL-SDR device object
        sample_rate (int): Current sample rate in samples per second
        center_freq (int): Current center frequency in Hz
        gain (float): Current gain setting in dB
        is_running (bool): Whether the device is actively streaming
    """
    
    # Common ham radio sample rates (Hz)
    SUPPORTED_SAMPLE_RATES = [48000, 96000, 192000, 256000, 512000, 1024000]
    
    # Gain range for typical RTL-SDR v3
    MIN_GAIN = 0.0
    MAX_GAIN = 49.6
    GAIN_STEP = 0.2
    
    def __init__(self, device_index: int = 0):
        """
        Initialize the RTL-SDR interface.
        
        Args:
            device_index: Index of the RTL-SDR device if multiple are connected.
                         Default is 0 (first device).
        
        Raises:
            RuntimeError: If no RTL-SDR devices are found or initialization fails.
        """
        if not RTLSDR_AVAILABLE:
            raise RuntimeError("pyrtlsdr library not available. Install with: pip install pyrtlsdr")
        
        self.device_index = device_index
        self.device: Optional[RtlSdr] = None
        self.sample_rate = 0
        self.center_freq = 0
        self.gain = 0.0
        self.is_running = False
        self._buffer_size = 1024
        
        logger.info(f"Initializing RTL-SDR interface (device index: {device_index})")
    
    def detect_devices(self) -> int:
        """
        Detect the number of RTL-SDR devices connected to the system.
        
        Returns:
            int: Number of RTL-SDR devices detected.
            
        Example:
            >>> iface = RtlsdrInterface()
            >>> count = iface.detect_devices()
            >>> print(f"Found {count} RTL-SDR devices")
        """
        try:
            count = RtlSdr.get_device_count()
            logger.info(f"Detected {count} RTL-SDR device(s)")
            return count
        except Exception as e:
            logger.error(f"Failed to detect devices: {e}")
            return 0
    
    def get_device_name(self, index: int = 0) -> str:
        """
        Get the name/string of a specific RTL-SDR device.
        
        Args:
            index: Device index to query.
            
        Returns:
            str: Device name string, or empty string if unavailable.
        """
        try:
            return RtlSdr.get_device_name(index)
        except Exception as e:
            logger.warning(f"Could not get device name for index {index}: {e}")
            return ""
    
    def initialize(self, sample_rate: int = 256000, center_freq: int = 7000000,
                   gain: Optional[float] = None, auto_gain: bool = False) -> bool:
        """
        Initialize and configure the RTL-SDR device.
        
        This method opens the device, sets the initial configuration,
        and prepares it for sampling.
        
        Args:
            sample_rate: Sample rate in samples per second (default: 256000).
                        Should be one of SUPPORTED_SAMPLE_RATES for best results.
            center_freq: Center frequency in Hz (default: 7 MHz - 40m band).
            gain: Manual gain setting in dB. If None and auto_gain=False,
                 uses device default.
            auto_gain: If True, enables automatic gain control (AGC).
                      If False, uses manual gain setting.
        
        Returns:
            bool: True if initialization successful, False otherwise.
            
        Raises:
            RuntimeError: If device cannot be opened or configured.
            
        Example:
            >>> iface = RtlsdrInterface()
            >>> success = iface.initialize(
            ...     sample_rate=256000,
            ...     center_freq=14200000,  # 20m band
            ...     gain=35.0,
            ...     auto_gain=False
            ... )
        """
        try:
            # Open device
            self.device = RtlSdr(device_index=self.device_index)
            logger.info(f"Opened RTL-SDR device {self.device_index}")
            
            # Set sample rate
            self.set_sample_rate(sample_rate)
            
            # Set center frequency
            self.set_center_frequency(center_freq)
            
            # Configure gain
            if auto_gain:
                self.set_auto_gain(True)
            elif gain is not None:
                self.set_manual_gain(gain)
            else:
                # Use device default gain
                self.gain = self.device.get_gain()
                logger.info(f"Using default gain: {self.gain} dB")
            
            # Reset buffer
            self.device.reset_buffer()
            
            self.is_running = True
            logger.info(f"RTL-SDR initialized: SR={sample_rate}, Freq={center_freq}, Gain={self.gain}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize RTL-SDR: {e}")
            self.close()
            return False
    
    def set_sample_rate(self, sample_rate: int) -> bool:
        """
        Set the sample rate of the RTL-SDR device.
        
        Args:
            sample_rate: New sample rate in samples per second.
            
        Returns:
            bool: True if successful, False otherwise.
        """
        try:
            if self.device is None:
                logger.error("Cannot set sample rate: device not initialized")
                return False
            
            self.device.set_sample_rate(sample_rate)
            self.sample_rate = sample_rate
            logger.debug(f"Sample rate set to {sample_rate} SPS")
            return True
        except Exception as e:
            logger.error(f"Failed to set sample rate: {e}")
            return False
    
    def set_center_frequency(self, frequency: int) -> bool:
        """
        Set the center frequency of the RTL-SDR device.
        
        Args:
            frequency: New center frequency in Hz.
            
        Returns:
            bool: True if successful, False otherwise.
            
        Example:
            >>> iface.set_center_frequency(7150000)  # 7.150 MHz
        """
        try:
            if self.device is None:
                logger.error("Cannot set frequency: device not initialized")
                return False
            
            self.device.set_center_freq(frequency)
            self.center_freq = frequency
            logger.debug(f"Center frequency set to {frequency} Hz ({frequency/1e6:.3f} MHz)")
            return True
        except Exception as e:
            logger.error(f"Failed to set center frequency: {e}")
            return False
    
    def set_manual_gain(self, gain: float) -> bool:
        """
        Set manual gain for the RTL-SDR device.
        
        Args:
            gain: Gain value in dB. Must be between MIN_GAIN and MAX_GAIN.
            
        Returns:
            bool: True if successful, False otherwise.
        """
        try:
            if self.device is None:
                logger.error("Cannot set gain: device not initialized")
                return False
            
            # Validate gain range
            gain = max(self.MIN_GAIN, min(self.MAX_GAIN, gain))
            
            self.device.set_manual_gain_mode()
            self.device.set_gain(gain)
            self.gain = gain
            logger.debug(f"Manual gain set to {gain} dB")
            return True
        except Exception as e:
            logger.error(f"Failed to set manual gain: {e}")
            return False
    
    def set_auto_gain(self, enable: bool = True) -> bool:
        """
        Enable or disable automatic gain control (AGC).
        
        Args:
            enable: If True, enables AGC. If False, disables AGC.
            
        Returns:
            bool: True if successful, False otherwise.
        """
        try:
            if self.device is None:
                logger.error("Cannot set gain mode: device not initialized")
                return False
            
            if enable:
                self.device.set_agc_mode(True)
                logger.debug("Auto gain (AGC) enabled")
            else:
                self.device.set_manual_gain_mode()
                logger.debug("Manual gain mode enabled")
            
            return True
        except Exception as e:
            logger.error(f"Failed to set gain mode: {e}")
            return False
    
    def read_samples(self, num_samples: int = 1024) -> Optional[np.ndarray]:
        """
        Read IQ samples from the RTL-SDR device.
        
        This is a blocking call that reads the specified number of samples.
        For continuous streaming, use stream_samples() instead.
        
        Args:
            num_samples: Number of IQ samples to read (default: 1024).
            
        Returns:
            numpy.ndarray: Array of complex IQ samples, or None if failed.
                          The array contains complex64 values normalized to [-1, 1].
                          
        Raises:
            RuntimeError: If device is not initialized or reading fails.
            
        Example:
            >>> samples = iface.read_samples(1024)
            >>> if samples is not None:
            ...     print(f"Read {len(samples)} samples")
            ...     power = np.mean(np.abs(samples)**2)
            ...     print(f"Signal power: {power}")
        """
        if self.device is None or not self.is_running:
            logger.error("Cannot read samples: device not running")
            return None
        
        try:
            raw_samples = self.device.read_samples(num_samples)
            # Convert to complex64 and normalize
            samples = raw_samples.astype(np.complex64) / 127.5 - 1.0 - 1j
            return samples
        except Exception as e:
            logger.error(f"Failed to read samples: {e}")
            # Attempt to recover device
            self._attempt_recovery()
            return None
    
    def stream_samples(self, num_samples: int = 1024) -> Generator[np.ndarray, None, None]:
        """
        Continuously stream IQ samples from the RTL-SDR device.
        
        This is a generator function that yields batches of IQ samples
        indefinitely until stopped. Use with care to avoid memory issues.
        
        Args:
            num_samples: Number of samples per batch (default: 1024).
            
        Yields:
            numpy.ndarray: Batches of complex IQ samples.
            
        Example:
            >>> for batch in iface.stream_samples(2048):
            ...     # Process each batch
            ...     if should_stop:
            ...         break
        """
        if self.device is None or not self.is_running:
            logger.error("Cannot stream samples: device not running")
            return
        
        try:
            for raw_samples in self.device.stream():
                # Convert and normalize
                samples = raw_samples.astype(np.complex64) / 127.5 - 1.0 - 1j
                yield samples
        except Exception as e:
            logger.error(f"Stream error: {e}")
            self._attempt_recovery()
    
    def get_signal_strength(self, num_samples: int = 1024) -> float:
        """
        Measure the current signal strength (RSSI).
        
        Args:
            num_samples: Number of samples to average over.
            
        Returns:
            float: Signal strength in dB (relative, not calibrated).
                  Higher values indicate stronger signals.
        """
        samples = self.read_samples(num_samples)
        if samples is None:
            return -100.0
        
        # Calculate mean power
        power = np.mean(np.abs(samples) ** 2)
        # Convert to dB (relative scale)
        rssi_db = 10 * np.log10(power + 1e-10)
        return rssi_db
    
    def _attempt_recovery(self) -> bool:
        """
        Attempt to recover from a device error by reinitializing.
        
        Returns:
            bool: True if recovery successful, False otherwise.
        """
        logger.warning("Attempting device recovery...")
        try:
            self.close()
            # Wait a moment for device to reset
            import time
            time.sleep(0.5)
            # Reinitialize with previous settings
            return self.initialize(
                sample_rate=self.sample_rate,
                center_freq=self.center_freq,
                gain=self.gain if self.gain > 0 else None
            )
        except Exception as e:
            logger.error(f"Device recovery failed: {e}")
            return False
    
    def close(self) -> None:
        """
        Close the RTL-SDR device and release resources.
        
        This should be called when finished with the device to properly
        release USB resources.
        
        Example:
            >>> try:
            ...     iface.initialize()
            ...     # ... use device ...
            ... finally:
            ...     iface.close()
        """
        self.is_running = False
        if self.device is not None:
            try:
                self.device.close()
                logger.info("RTL-SDR device closed")
            except Exception as e:
                logger.warning(f"Error closing device: {e}")
            finally:
                self.device = None
    
    def get_status(self) -> dict:
        """
        Get current device status information.
        
        Returns:
            dict: Dictionary containing device status:
                - 'initialized': bool - Whether device is initialized
                - 'running': bool - Whether device is streaming
                - 'sample_rate': int - Current sample rate
                - 'center_freq': int - Current center frequency
                - 'gain': float - Current gain setting
                - 'device_name': str - Device name string
        """
        return {
            'initialized': self.device is not None,
            'running': self.is_running,
            'sample_rate': self.sample_rate,
            'center_freq': self.center_freq,
            'gain': self.gain,
            'device_name': self.get_device_name(self.device_index) if self.device else "N/A"
        }
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - ensures device is closed."""
        self.close()
        return False  # Don't suppress exceptions


# Convenience function for quick testing
def test_rtlsdr_connection(device_index: int = 0) -> bool:
    """
    Quick test function to verify RTL-SDR connectivity.
    
    Args:
        device_index: Device index to test.
        
    Returns:
        bool: True if device is accessible and functional, False otherwise.
        
    Example:
        >>> if test_rtlsdr_connection():
        ...     print("RTL-SDR is ready!")
        ... else:
        ...     print("Check your RTL-SDR connection")
    """
    try:
        iface = RtlsdrInterface(device_index)
        count = iface.detect_devices()
        if count == 0:
            print("No RTL-SDR devices found!")
            return False
        
        print(f"Found {count} RTL-SDR device(s)")
        print(f"Device name: {iface.get_device_name(device_index)}")
        
        if iface.initialize(sample_rate=256000, center_freq=7000000, auto_gain=True):
            print("Successfully initialized!")
            
            # Test sample read
            samples = iface.read_samples(1024)
            if samples is not None:
                print(f"Successfully read {len(samples)} samples")
                rssi = iface.get_signal_strength()
                print(f"Signal strength: {rssi:.2f} dB")
            
            iface.close()
            return True
        else:
            print("Failed to initialize device")
            return False
            
    except Exception as e:
        print(f"Test failed: {e}")
        return False


if __name__ == "__main__":
    # Basic test when run directly
    logging.basicConfig(level=logging.INFO)
    success = test_rtlsdr_connection()
    exit(0 if success else 1)
