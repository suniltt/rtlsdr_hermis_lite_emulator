"""
Main Application Module

This is the main entry point for the RTL-Hermes Emulator.
It integrates all components and manages the application lifecycle.

Usage:
    python main.py [--config CONFIG_FILE] [--host HOST] [--port PORT]

Author: RTL-Hermes Emulator Project
License: GPL-3.0
"""

import logging
import argparse
import signal
import sys
import time
import json
from pathlib import Path
from typing import Optional, Dict, Any

# Import our modules
from rtlsdr_interface import RtlsdrInterface, test_rtlsdr_connection
from signal_processor import SignalProcessor
from hpsdr_protocol import HPSDRProtocolHandler, IQPacketBuilder, DiscoveryServer
from network_server import DataStreamServer, ControlServer


class RTLHermesEmulator:
    """
    Main application class that integrates all components.
    
    This class coordinates:
    - RTL-SDR hardware interface
    - Signal processing (decimation, filtering)
    - HPSDR protocol emulation
    - Network streaming
    
    Attributes:
        config: Configuration dictionary
        rtlsdr: RTL-SDR interface instance
        processor: Signal processor instance
        protocol_handler: HPSDR protocol handler
        discovery_server: UDP discovery server
        data_server: TCP data streaming server
        control_server: TCP control server
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the emulator with configuration.
        
        Args:
            config: Configuration dictionary with keys:
                - 'rtlsdr_device': RTL-SDR device index (default: 0)
                - 'sample_rate': RTL-SDR sample rate (default: 256000)
                - 'output_rate': HPSDR output rate (default: 48000)
                - 'frequency': Initial frequency in Hz (default: 7000000)
                - 'gain': Initial gain in dB (default: 20.0)
                - 'auto_gain': Enable AGC (default: False)
                - 'network_host': Network interface (default: '0.0.0.0')
                - 'network_port': Network port (default: 1024)
                - 'device_name': Device name for discovery (default: 'RTL-Hermes')
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Components (initialized in start())
        self.rtlsdr: Optional[RtlsdrInterface] = None
        self.processor: Optional[SignalProcessor] = None
        self.protocol_handler: Optional[HPSDRProtocolHandler] = None
        self.discovery_server: Optional[DiscoveryServer] = None
        self.data_server: Optional[DataStreamServer] = None
        self.control_server: Optional[ControlServer] = None
        self.iq_builder: Optional[IQPacketBuilder] = None
        
        # State
        self.running = False
        self._stream_thread: Optional[threading.Thread] = None
        
        self.logger.info("RTL-Hermes Emulator initialized")
    
    def start(self) -> bool:
        """
        Start all components and begin operation.
        
        Returns:
            bool: True if all components started successfully.
        """
        self.logger.info("Starting RTL-Hermes Emulator...")
        
        try:
            # Initialize RTL-SDR
            if not self._init_rtlsdr():
                return False
            
            # Initialize signal processor
            if not self._init_processor():
                return False
            
            # Initialize HPSDR protocol
            if not self._init_protocol():
                return False
            
            # Initialize network servers
            if not self._init_network():
                return False
            
            # Setup callbacks
            self._setup_callbacks()
            
            # Start IQ streaming thread
            self.running = True
            self._stream_thread = threading.Thread(
                target=self._stream_iq_loop,
                daemon=True
            )
            self._stream_thread.start()
            
            self.logger.info("RTL-Hermes Emulator started successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start emulator: {e}")
            self.stop()
            return False
    
    def stop(self) -> None:
        """Stop all components and cleanup."""
        self.logger.info("Stopping RTL-Hermes Emulator...")
        
        self.running = False
        
        # Stop streaming thread
        if self._stream_thread:
            self._stream_thread.join(timeout=2.0)
        
        # Stop servers
        if self.data_server:
            self.data_server.stop()
        if self.control_server:
            self.control_server.stop()
        if self.discovery_server:
            self.discovery_server.stop()
        
        # Close RTL-SDR
        if self.rtlsdr:
            self.rtlsdr.close()
        
        self.logger.info("RTL-Hermes Emulator stopped")
    
    def _init_rtlsdr(self) -> bool:
        """Initialize RTL-SDR hardware."""
        self.logger.info("Initializing RTL-SDR...")
        
        self.rtlsdr = RtlsdrInterface(
            device_index=self.config.get('rtlsdr_device', 0)
        )
        
        # Check for devices
        count = self.rtlsdr.detect_devices()
        if count == 0:
            self.logger.error("No RTL-SDR devices found!")
            return False
        
        self.logger.info(f"Found {count} RTL-SDR device(s)")
        
        # Initialize device
        success = self.rtlsdr.initialize(
            sample_rate=self.config.get('sample_rate', 256000),
            center_freq=self.config.get('frequency', 7000000),
            gain=self.config.get('gain', 20.0),
            auto_gain=self.config.get('auto_gain', False)
        )
        
        if not success:
            self.logger.error("Failed to initialize RTL-SDR")
            return False
        
        status = self.rtlsdr.get_status()
        self.logger.info(f"RTL-SDR status: {status}")
        
        return True
    
    def _init_processor(self) -> bool:
        """Initialize signal processor."""
        self.logger.info("Initializing signal processor...")
        
        input_rate = self.config.get('sample_rate', 256000)
        output_rate = self.config.get('output_rate', 48000)
        
        self.processor = SignalProcessor(
            input_rate=input_rate,
            output_rate=output_rate
        )
        
        # Enable AGC if configured
        if self.config.get('auto_gain', False):
            self.processor.enable_agc(
                enable=True,
                target_level=0.5
            )
        
        self.logger.info(f"Signal processor ready: {input_rate} -> {output_rate}")
        return True
    
    def _init_protocol(self) -> bool:
        """Initialize HPSDR protocol handler."""
        self.logger.info("Initializing HPSDR protocol...")
        
        device_name = self.config.get('device_name', 'RTL-Hermes')
        self.protocol_handler = HPSDRProtocolHandler(device_name=device_name)
        
        # Set initial frequency
        freq = self.config.get('frequency', 7000000)
        self.protocol_handler.set_frequency(freq)
        
        self.iq_builder = IQPacketBuilder()
        
        self.logger.info(f"HPSDR protocol handler ready: {device_name}")
        return True
    
    def _init_network(self) -> bool:
        """Initialize network servers."""
        self.logger.info("Initializing network servers...")
        
        host = self.config.get('network_host', '0.0.0.0')
        port = self.config.get('network_port', 1024)
        
        # Start discovery server
        self.discovery_server = DiscoveryServer(
            handler=self.protocol_handler,
            interface=host,
            port=port
        )
        
        if not self.discovery_server.start():
            self.logger.error("Failed to start discovery server")
            return False
        
        # Start data server
        self.data_server = DataStreamServer(
            host=host,
            port=port,
            max_clients=4
        )
        
        if not self.data_server.start():
            self.logger.error("Failed to start data server")
            return False
        
        # Start control server (multiplexed with data on same port)
        self.control_server = ControlServer(
            host=host,
            port=port,
            command_handler=self.protocol_handler.parse_command
        )
        
        if not self.control_server.start():
            self.logger.error("Failed to start control server")
            return False
        
        self.logger.info(f"Network servers running on {host}:{port}")
        return True
    
    def _setup_callbacks(self) -> None:
        """Setup event callbacks between components."""
        
        # Frequency change callback
        def on_freq_change(freq: int):
            if self.rtlsdr:
                self.rtlsdr.set_center_frequency(freq)
            if self.processor:
                self.processor.reset()
        
        self.protocol_handler.on_frequency_change = on_freq_change
        
        # Gain change callback
        def on_gain_change(gain: float):
            if self.rtlsdr:
                self.rtlsdr.set_manual_gain(gain)
        
        self.protocol_handler.on_gain_change = on_gain_change
        
        # Sample rate change callback
        def on_rate_change(rate: int):
            if self.processor:
                self.processor.set_output_rate(rate)
        
        self.protocol_handler.on_sample_rate_change = on_rate_change
        
        # RX start/stop callbacks
        def on_start_rx():
            self.logger.info("RX started by client")
            if self.iq_builder:
                self.iq_builder.reset_sequence()
        
        def on_stop_rx():
            self.logger.info("RX stopped by client")
        
        self.protocol_handler.on_start_rx = on_start_rx
        self.protocol_handler.on_stop_rx = on_stop_rx
    
    def _stream_iq_loop(self) -> None:
        """Main loop for reading and streaming IQ data."""
        self.logger.info("IQ streaming thread started")
        
        # Calculate batch size for smooth streaming
        # Target: ~10ms of audio per batch at output rate
        output_rate = self.config.get('output_rate', 48000)
        batch_size_output = output_rate // 100  # 10ms
        
        # Convert to input samples needed
        input_rate = self.config.get('sample_rate', 256000)
        decimation = input_rate // output_rate
        batch_size_input = batch_size_output * decimation
        
        accumulation_buffer = []
        
        while self.running:
            try:
                # Read samples from RTL-SDR
                if self.rtlsdr:
                    samples = self.rtlsdr.read_samples(batch_size_input)
                    
                    if samples is None or len(samples) == 0:
                        time.sleep(0.01)  # Brief pause on error
                        continue
                    
                    # Process samples
                    if self.processor:
                        processed = self.processor.process_samples(samples)
                        
                        if len(processed) > 0:
                            accumulation_buffer.extend(processed)
                            
                            # When we have enough for a packet
                            min_for_packet = 504  # Samples per packet
                            while len(accumulation_buffer) >= min_for_packet:
                                packet_samples = accumulation_buffer[:min_for_packet]
                                accumulation_buffer = accumulation_buffer[min_for_packet:]
                                
                                # Format for HPSDR
                                iq_bytes = self.processor.format_iq_for_hpsdr(
                                    np.array(packet_samples)
                                )
                                
                                # Build packet
                                if self.iq_builder:
                                    packet = self.iq_builder.build_packet(iq_bytes)
                                    
                                    # Send to all clients
                                    if self.data_server:
                                        self.data_server.send_to_all_clients(packet)
                
                else:
                    time.sleep(0.1)
                    
            except Exception as e:
                self.logger.error(f"Error in IQ streaming loop: {e}")
                time.sleep(0.1)
        
        self.logger.info("IQ streaming thread stopped")
    
    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive system status."""
        status = {
            'running': self.running,
            'config': self.config,
        }
        
        if self.rtlsdr:
            status['rtlsdr'] = self.rtlsdr.get_status()
        
        if self.processor:
            status['processor'] = self.processor.get_statistics()
        
        if self.protocol_handler:
            status['protocol'] = self.protocol_handler.get_state()
        
        if self.data_server:
            status['network'] = self.data_server.get_statistics()
        
        return status
    
    def run_forever(self) -> None:
        """Run the emulator until interrupted."""
        if not self.start():
            sys.exit(1)
        
        self.logger.info("Emulator running. Press Ctrl+C to stop.")
        
        try:
            while self.running:
                time.sleep(1)
                
                # Periodic status update
                stats = self.get_status()
                if 'network' in stats:
                    clients = stats['network'].get('connected_clients', 0)
                    if clients > 0:
                        self.logger.debug(f"Active clients: {clients}")
                        
        except KeyboardInterrupt:
            self.logger.info("Interrupt received")
        finally:
            self.stop()


def load_config(config_file: str) -> Dict[str, Any]:
    """Load configuration from JSON file."""
    path = Path(config_file)
    if not path.exists():
        return {}
    
    with open(path, 'r') as f:
        return json.load(f)


def main():
    """Main entry point."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description='RTL-SDR to Hermes-Lite Emulator'
    )
    parser.add_argument(
        '--config', '-c',
        type=str,
        default='config.json',
        help='Configuration file (JSON)'
    )
    parser.add_argument(
        '--host',
        type=str,
        default=None,
        help='Network host/interface to bind to'
    )
    parser.add_argument(
        '--port', '-p',
        type=int,
        default=None,
        help='Network port (default: 1024)'
    )
    parser.add_argument(
        '--frequency', '-f',
        type=int,
        default=None,
        help='Initial frequency in Hz'
    )
    parser.add_argument(
        '--gain', '-g',
        type=float,
        default=None,
        help='Initial gain in dB'
    )
    parser.add_argument(
        '--device', '-d',
        type=int,
        default=None,
        help='RTL-SDR device index'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    parser.add_argument(
        '--test',
        action='store_true',
        help='Test RTL-SDR connection and exit'
    )
    
    args = parser.parse_args()
    
    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    logger = logging.getLogger(__name__)
    
    # Test mode
    if args.test:
        print("Testing RTL-SDR connection...")
        success = test_rtlsdr_connection()
        sys.exit(0 if success else 1)
    
    # Load configuration
    config = load_config(args.config)
    
    # Override with command line arguments
    if args.host:
        config['network_host'] = args.host
    if args.port:
        config['network_port'] = args.port
    if args.frequency:
        config['frequency'] = args.frequency
    if args.gain:
        config['gain'] = args.gain
    if args.device is not None:
        config['rtlsdr_device'] = args.device
    
    # Set defaults
    config.setdefault('rtlsdr_device', 0)
    config.setdefault('sample_rate', 256000)
    config.setdefault('output_rate', 48000)
    config.setdefault('frequency', 7000000)
    config.setdefault('gain', 20.0)
    config.setdefault('auto_gain', False)
    config.setdefault('network_host', '0.0.0.0')
    config.setdefault('network_port', 1024)
    config.setdefault('device_name', 'RTL-Hermes')
    
    logger.info(f"Configuration: {config}")
    
    # Create and run emulator
    emulator = RTLHermesEmulator(config)
    emulator.run_forever()


if __name__ == '__main__':
    main()
