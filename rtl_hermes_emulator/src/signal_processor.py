"""
Signal Processor Module

This module handles digital signal processing operations including:
- Sample rate conversion (decimation)
- Digital filtering (FIR, CIC)
- Frequency translation
- AGC (Automatic Gain Control)
- IQ data formatting for HPSDR protocol

Author: RTL-Hermes Emulator Project
License: GPL-3.0
"""

import logging
from typing import Optional, Tuple
import numpy as np
from scipy import signal
from collections import deque

logger = logging.getLogger(__name__)


class SignalProcessor:
    """
    Digital signal processor for RTL-SDR to HPSDR conversion.
    
    This class performs the necessary DSP operations to convert
    high-rate RTL-SDR samples to HPSDR-compatible output rates.
    
    Key Operations:
    - Decimation: Reduce sample rate from RTL-SDR (e.g., 256 kHz) 
                  to HPSDR rates (48-192 kHz)
    - Filtering: Anti-aliasing and channel selection filters
    - Frequency Translation: Shift spectrum if needed
    - AGC: Automatic gain control for consistent output levels
    
    Attributes:
        input_sample_rate (int): Input sample rate from RTL-SDR
        output_sample_rate (int): Output sample rate for HPSDR
        decimation_factor (int): Ratio of input/output sample rates
        filter_order (int): Order of the decimation filter
    """
    
    # Standard HPSDR output sample rates
    HPSDR_SAMPLE_RATES = [48000, 96000, 192000]
    
    def __init__(self, input_rate: int = 256000, output_rate: int = 48000):
        """
        Initialize the signal processor.
        
        Args:
            input_rate: Input sample rate from RTL-SDR in Hz (default: 256000).
            output_rate: Desired output sample rate for HPSDR in Hz (default: 48000).
                        Must be one of HPSDR_SAMPLE_RATES.
        
        Raises:
            ValueError: If output_rate is not supported or decimation ratio is invalid.
            
        Example:
            >>> proc = SignalProcessor(input_rate=256000, output_rate=48000)
            >>> print(f"Decimation factor: {proc.decimation_factor}")
        """
        self.input_sample_rate = input_rate
        self.output_sample_rate = output_rate
        
        if output_rate not in self.HPSDR_SAMPLE_RATES:
            logger.warning(f"Output rate {output_rate} not standard. Using nearest supported rate.")
            # Find nearest supported rate
            output_rate = min(self.HPSDR_SAMPLE_RATES, 
                            key=lambda x: abs(x - output_rate))
            self.output_sample_rate = output_rate
        
        # Calculate decimation factor
        self.decimation_factor = input_rate // output_rate
        if input_rate % output_rate != 0:
            logger.warning(f"Non-integer decimation ratio: {input_rate}/{output_rate}")
            # Adjust input rate for integer decimation
            self.input_sample_rate = self.decimation_factor * output_rate
        
        logger.info(f"Signal processor initialized: {input_rate} -> {output_rate} "
                   f"(decimation: {self.decimation_factor})")
        
        # Initialize filter
        self._setup_filter()
        
        # Initialize AGC
        self.agc_enabled = False
        self.agc_target_level = 0.5  # Target RMS level
        self.agc_attack = 0.01       # Fast attack
        self.agc_decay = 0.001       # Slow decay
        self.agc_gain = 1.0
        
        # Buffer for partial blocks
        self._buffer = deque(maxlen=input_rate)
        
        # Statistics
        self.samples_processed = 0
        self.clips_detected = 0
    
    def _setup_filter(self, cutoff_ratio: float = 0.8) -> None:
        """
        Design and setup the decimation filter.
        
        Uses a FIR filter with Kaiser window for good stopband attenuation.
        
        Args:
            cutoff_ratio: Normalized cutoff frequency as fraction of Nyquist
                         after decimation (default: 0.8).
        
        The filter is designed to:
        - Pass frequencies up to output_rate/2 * cutoff_ratio
        - Attenuate frequencies above output_rate/2 to prevent aliasing
        """
        # Nyquist frequency after decimation
        nyquist_out = self.output_sample_rate / 2
        
        # Cutoff frequency
        cutoff = nyquist_out * cutoff_ratio
        
        # Normalize cutoff relative to input Nyquist
        normalized_cutoff = cutoff / (self.input_sample_rate / 2)
        
        # Filter order (higher = sharper transition, more CPU)
        # Rule of thumb: order ≈ 4 * decimation_factor
        self.filter_order = max(63, 4 * self.decimation_factor)
        # Ensure odd order for linear phase
        if self.filter_order % 2 == 0:
            self.filter_order += 1
        
        # Design FIR filter with Kaiser window
        try:
            self.filter_coeffs = signal.firwin(
                numtaps=self.filter_order,
                cutoff=normalized_cutoff,
                window='kaiser',
                beta=8.6,  # Good stopband attenuation (~80 dB)
                pass_zero=True
            )
            logger.debug(f"Filter designed: order={self.filter_order}, "
                        f"cutoff={cutoff:.0f} Hz")
        except Exception as e:
            logger.error(f"Filter design failed: {e}")
            # Fallback to simple moving average
            self.filter_order = self.decimation_factor
            self.filter_coeffs = np.ones(self.filter_order) / self.filter_order
    
    def set_output_rate(self, output_rate: int) -> bool:
        """
        Change the output sample rate.
        
        Args:
            output_rate: New output sample rate in Hz.
            
        Returns:
            bool: True if successful, False if rate change failed.
        """
        if output_rate == self.output_sample_rate:
            return True
        
        if output_rate not in self.HPSDR_SAMPLE_RATES:
            logger.error(f"Unsupported output rate: {output_rate}")
            return False
        
        old_rate = self.output_sample_rate
        self.output_sample_rate = output_rate
        self.decimation_factor = self.input_sample_rate // output_rate
        
        # Redesign filter for new rate
        self._setup_filter()
        
        # Clear buffer to avoid artifacts
        self._buffer.clear()
        
        logger.info(f"Output rate changed: {old_rate} -> {output_rate}")
        return True
    
    def process_samples(self, samples: np.ndarray) -> np.ndarray:
        """
        Process a block of input samples through decimation and filtering.
        
        This is the main processing function. It takes high-rate samples
        from the RTL-SDR and outputs lower-rate samples suitable for HPSDR.
        
        Args:
            samples: Input complex IQ samples as numpy array.
                    Should be complex64 or complex128.
        
        Returns:
            numpy.ndarray: Decimated and filtered complex IQ samples.
                          Length will be len(samples) // decimation_factor.
                          
        Example:
            >>> proc = SignalProcessor(256000, 48000)
            >>> input_samples = rtl_sdr.read_samples(2560)  # 10ms at 256 kHz
            >>> output_samples = proc.process_samples(input_samples)
            >>> print(f"Output: {len(output_samples)} samples at 48 kHz")
        """
        if len(samples) == 0:
            return np.array([], dtype=np.complex64)
        
        # Add to buffer
        self._buffer.extend(samples)
        self.samples_processed += len(samples)
        
        # Need enough samples for decimation
        if len(self._buffer) < self.decimation_factor:
            return np.array([], dtype=np.complex64)
        
        # Convert buffer to array
        buffer_array = np.array(self._buffer, dtype=np.complex64)
        
        # Apply anti-aliasing filter
        try:
            # Filter I and Q separately to maintain phase relationship
            i_filtered = signal.lfilter(self.filter_coeffs, 1.0, buffer_array.real)
            q_filtered = signal.lfilter(self.filter_coeffs, 1.0, buffer_array.imag)
            filtered = i_filtered + 1j * q_filtered
        except Exception as e:
            logger.error(f"Filtering error: {e}")
            filtered = buffer_array
        
        # Decimate by taking every Nth sample
        decimated = filtered[::self.decimation_factor]
        
        # Apply AGC if enabled
        if self.agc_enabled:
            decimated = self._apply_agc(decimated)
        
        # Keep only the samples we've processed
        samples_to_remove = (len(decimated) * self.decimation_factor)
        for _ in range(min(samples_to_remove, len(self._buffer))):
            self._buffer.popleft()
        
        # Check for clipping
        if np.any(np.abs(decimated) > 1.0):
            self.clips_detected += np.sum(np.abs(decimated) > 1.0)
            # Soft clip to prevent harsh distortion
            decimated = self._soft_clip(decimated)
        
        return decimated.astype(np.complex64)
    
    def _apply_agc(self, samples: np.ndarray) -> np.ndarray:
        """
        Apply automatic gain control to samples.
        
        Uses a simple RMS-based AGC with separate attack and decay times.
        
        Args:
            samples: Input complex IQ samples.
            
        Returns:
            numpy.ndarray: AGC-adjusted samples.
        """
        if len(samples) == 0:
            return samples
        
        # Calculate RMS level
        rms = np.sqrt(np.mean(np.abs(samples) ** 2))
        
        if rms < 1e-10:
            return samples
        
        # Calculate error from target
        error = self.agc_target_level - rms
        
        # Adjust gain based on error
        if error > 0:
            # Signal too weak - increase gain (fast attack)
            self.agc_gain *= (1.0 + self.agc_attack * error)
        else:
            # Signal too strong - decrease gain (slow decay)
            self.agc_gain *= (1.0 + self.agc_decay * error)
        
        # Limit gain to reasonable range
        self.agc_gain = np.clip(self.agc_gain, 0.1, 10.0)
        
        # Apply gain
        return samples * self.agc_gain
    
    def _soft_clip(self, samples: np.ndarray, threshold: float = 0.95) -> np.ndarray:
        """
        Apply soft clipping to prevent harsh digital distortion.
        
        Uses a tanh-based soft clipper for smooth saturation.
        
        Args:
            samples: Input samples that may exceed threshold.
            threshold: Clipping threshold (default: 0.95).
            
        Returns:
            numpy.ndarray: Soft-clipped samples.
        """
        magnitude = np.abs(samples)
        mask = magnitude > threshold
        
        if not np.any(mask):
            return samples
        
        # Apply soft clipping using tanh
        clipped = samples.copy()
        clipped[mask] = np.tanh(samples[mask] / threshold) * threshold
        
        return clipped
    
    def frequency_translate(self, samples: np.ndarray, freq_offset: float) -> np.ndarray:
        """
        Translate the frequency of samples by a given offset.
        
        This is useful for tuning within the RTL-SDR's instantaneous bandwidth
        without changing the hardware frequency.
        
        Args:
            samples: Input complex IQ samples.
            freq_offset: Frequency shift in Hz. Positive shifts up, negative down.
            
        Returns:
            numpy.ndarray: Frequency-shifted samples.
            
        Example:
            >>> # Shift spectrum up by 5 kHz
            >>> shifted = proc.frequency_translate(samples, 5000)
        """
        if freq_offset == 0:
            return samples
        
        # Create complex exponential for mixing
        t = np.arange(len(samples)) / self.input_sample_rate
        mixer = np.exp(1j * 2 * np.pi * freq_offset * t)
        
        # Mix (multiply) input with local oscillator
        translated = samples * mixer
        
        return translated
    
    def get_spectrum(self, samples: np.ndarray, fft_size: int = 1024) -> np.ndarray:
        """
        Compute power spectrum of samples using FFT.
        
        Useful for visualization or signal detection.
        
        Args:
            samples: Input complex IQ samples.
            fft_size: Size of FFT (default: 1024). Should be power of 2.
            
        Returns:
            numpy.ndarray: Power spectrum in dB, length fft_size//2 + 1
        """
        # Ensure fft_size is power of 2
        fft_size = 2 ** int(np.log2(fft_size))
        
        # Take FFT
        fft_data = np.fft.rfft(samples[:fft_size] if len(samples) >= fft_size 
                               else np.pad(samples, (0, fft_size - len(samples))))
        
        # Calculate power spectrum
        power = np.abs(fft_data) ** 2
        
        # Convert to dB
        spectrum_db = 10 * np.log10(power + 1e-10)
        
        return spectrum_db
    
    def enable_agc(self, enable: bool = True, target_level: float = 0.5,
                   attack: float = 0.01, decay: float = 0.001) -> None:
        """
        Configure and enable/disable AGC.
        
        Args:
            enable: Whether to enable AGC.
            target_level: Target RMS level (0.0 to 1.0).
            attack: Attack rate (higher = faster gain increase).
            decay: Decay rate (higher = faster gain decrease).
        """
        self.agc_enabled = enable
        self.agc_target_level = target_level
        self.agc_attack = attack
        self.agc_decay = decay
        
        if enable:
            logger.info(f"AGC enabled: target={target_level}, "
                       f"attack={attack}, decay={decay}")
        else:
            logger.info("AGC disabled")
            self.agc_gain = 1.0  # Reset gain
    
    def reset(self) -> None:
        """
        Reset the processor state.
        
        Clears buffers and resets AGC gain. Call when changing
        frequency or other major parameters.
        """
        self._buffer.clear()
        self.agc_gain = 1.0
        self.samples_processed = 0
        self.clips_detected = 0
        logger.debug("Signal processor reset")
    
    def get_statistics(self) -> dict:
        """
        Get processing statistics.
        
        Returns:
            dict: Statistics including:
                - 'samples_processed': Total samples processed
                - 'clips_detected': Number of clipping events
                - 'agc_gain': Current AGC gain (if enabled)
                - 'buffer_size': Current buffer fill level
        """
        return {
            'samples_processed': self.samples_processed,
            'clips_detected': self.clips_detected,
            'agc_gain': self.agc_gain if self.agc_enabled else 1.0,
            'agc_enabled': self.agc_enabled,
            'buffer_size': len(self._buffer),
            'decimation_factor': self.decimation_factor,
            'filter_order': self.filter_order
        }
    
    def format_iq_for_hpsdr(self, samples: np.ndarray) -> bytes:
        """
        Format IQ samples for HPSDR protocol transmission.
        
        Converts complex samples to interleaved 16-bit I/Q pairs
        as required by the HPSDR protocol.
        
        Args:
            samples: Complex IQ samples (normalized to -1.0 to 1.0).
            
        Returns:
            bytes: Binary data with interleaved I16/Q16 samples.
                  Each sample pair is 4 bytes (2 bytes I + 2 bytes Q).
        
        Example:
            >>> samples = proc.process_samples(rtl_samples)
            >>> hpsdr_data = proc.format_iq_for_hpsdr(samples)
            >>> # Send hpsdr_data over network
        """
        if len(samples) == 0:
            return b''
        
        # Scale to 16-bit range (-32768 to 32767)
        i_samples = (samples.real * 32767).astype(np.int16)
        q_samples = (samples.imag * 32767).astype(np.int16)
        
        # Interleave I and Q
        iq_interleaved = np.empty((len(samples), 2), dtype=np.int16)
        iq_interleaved[:, 0] = i_samples
        iq_interleaved[:, 1] = q_samples
        
        # Convert to bytes (little-endian)
        return iq_interleaved.tobytes()


class BandpassFilter:
    """
    Configurable bandpass filter for ham radio bands.
    
    Provides preset filters for common amateur radio bands
    to improve signal-to-noise ratio and reduce interference.
    """
    
    # Common ham radio band definitions (Hz)
    BANDS = {
        '160m': (1800000, 2000000),
        '80m': (3500000, 4000000),
        '60m': (5250000, 5450000),
        '40m': (7000000, 7300000),
        '30m': (10100000, 10150000),
        '20m': (14000000, 14350000),
        '17m': (18068000, 18168000),
        '15m': (21000000, 21450000),
        '12m': (24890000, 24990000),
        '10m': (28000000, 29700000),
        '6m': (50000000, 54000000),
        '2m': (144000000, 148000000),
        '70cm': (420000000, 450000000),
    }
    
    def __init__(self, sample_rate: int, center_freq: float, bandwidth: float):
        """
        Initialize a bandpass filter.
        
        Args:
            sample_rate: Sample rate in Hz.
            center_freq: Center frequency of desired band in Hz.
            bandwidth: Filter bandwidth in Hz.
        """
        self.sample_rate = sample_rate
        self.center_freq = center_freq
        self.bandwidth = bandwidth
        
        self._design_filter()
    
    def _design_filter(self) -> None:
        """Design the bandpass filter coefficients."""
        # Normalize frequencies
        nyquist = self.sample_rate / 2
        low = (self.center_freq - self.bandwidth/2) / nyquist
        high = (self.center_freq + self.bandwidth/2) / nyquist
        
        # Clamp to valid range
        low = max(0.001, min(0.999, low))
        high = max(0.001, min(0.999, high))
        
        # Design filter
        order = min(101, max(31, int(self.sample_rate / self.bandwidth)))
        if order % 2 == 0:
            order += 1
        
        self.coeffs = signal.firwin(order, [low, high], pass_zero=False)
    
    def apply(self, samples: np.ndarray) -> np.ndarray:
        """Apply the bandpass filter to samples."""
        return signal.lfilter(self.coeffs, 1.0, samples)


if __name__ == "__main__":
    # Test the signal processor
    logging.basicConfig(level=logging.INFO)
    
    # Create test signal (simulated)
    fs = 256000  # 256 kHz sample rate
    t = np.linspace(0, 0.1, int(0.1 * fs))  # 100 ms
    f_signal = 7000  # 7 kHz tone
    
    # Generate test IQ signal
    test_signal = np.exp(1j * 2 * np.pi * f_signal * t) * 0.5
    
    # Process through signal processor
    proc = SignalProcessor(input_rate=256000, output_rate=48000)
    output = proc.process_samples(test_signal)
    
    print(f"Input: {len(test_signal)} samples at {fs} Hz")
    print(f"Output: {len(output)} samples at {proc.output_sample_rate} Hz")
    print(f"Decimation factor: {proc.decimation_factor}")
    print(f"Statistics: {proc.get_statistics()}")
    
    # Test HPSDR formatting
    hpsdr_bytes = proc.format_iq_for_hpsdr(output)
    print(f"HPSDR formatted: {len(hpsdr_bytes)} bytes")
