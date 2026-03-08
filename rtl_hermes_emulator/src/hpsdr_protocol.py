"""
HPSDR Protocol Emulation Module

This module implements the Hermes-Lite/HPSDR protocol for compatibility
with HPSDR client software like PowerSDR, Quisk, and Thetis.

Protocol Specification:
- Discovery: UDP broadcast on port 1024
- Control/Data: TCP connection on port 1024
- Packet format: 1024-byte packets with header + IQ samples

Author: RTL-Hermes Emulator Project
License: GPL-3.0
"""

import logging
import struct
import socket
import threading
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass, field
from enum import IntEnum
import time

logger = logging.getLogger(__name__)


# HPSDR Protocol Constants
HERMES_DISCOVERY_PORT = 1024
HERMES_DATA_PORT = 1024
PACKET_SIZE = 1024
IQ_SAMPLES_PER_PACKET = 504  # 504 I/Q pairs per packet (16-bit each)


class HermesCommand(IntEnum):
    """Hermes-Lite command codes."""
    DISCOVERY = 0x00
    STOP = 0x01
    PROGRAM = 0x02
    MANUAL_READ = 0x03
    MANUAL_WRITE = 0x04
    READ_ADDRESS = 0x05
    WRITE_ADDRESS = 0x06
    START_RX = 0x07
    STOP_RX = 0x08


@dataclass
class HermesDevice:
    """
    Represents a Hermes-compatible device for discovery.
    
    Attributes:
        name: Device name string (max 16 chars)
        mac_address: MAC address as bytes (6 bytes)
        ip_address: IP address string
        port: Port number
        sample_rate: Current sample rate
        adc_frequency: ADC clock frequency
        firmware_version: Firmware version string
        status: Device status flags
    """
    name: str = "RTL-Hermes"
    mac_address: bytes = b'\x00\x00\x00\x00\x00\x00'
    ip_address: str = "0.0.0.0"
    port: int = HERMES_DATA_PORT
    sample_rate: int = 48000
    adc_frequency: int = 122880000
    firmware_version: str = "0.1.0"
    status: int = 0x00
    
    def to_discovery_response(self) -> bytes:
        """
        Create discovery response packet.
        
        Returns:
            bytes: 60-byte discovery response packet
        """
        # Discovery response format:
        # [0]: Command (0x02 for response)
        # [1]: Status
        # [2-7]: MAC address
        # [8-23]: Device name (16 bytes, null-padded)
        # [24-27]: ADC frequency
        # [28-31]: Sample rate
        # [32-35]: Firmware version (as integer)
        # [36-59]: Reserved/padding
        
        name_bytes = self.name.encode('ascii')[:16].ljust(16, b'\x00')
        
        # Parse firmware version to integer
        try:
            version_parts = [int(x) for x in self.firmware_version.split('.')]
            version_int = (version_parts[0] << 16) | (version_parts[1] << 8) | version_parts[2]
        except:
            version_int = 0x000100
        
        packet = struct.pack(
            '>B B 6s 16s I I I',
            0x02,  # Response command
            self.status,
            self.mac_address,
            name_bytes,
            self.adc_frequency,
            self.sample_rate,
            version_int
        )
        
        # Pad to 60 bytes
        packet = packet.ljust(60, b'\x00')
        
        return packet


@dataclass
class ControlState:
    """
    Current control state of the emulated Hermes device.
    
    Tracks all configurable parameters that can be set via
    HPSDR protocol commands.
    """
    frequency: int = 7000000  # 7 MHz default
    gain: float = 20.0
    sample_rate: int = 48000
    running: bool = False
    agc_enabled: bool = False
    filter_low: int = 0
    filter_high: int = 48000
    ptt_enabled: bool = False  # Always False for receive-only
    bias_tee_enabled: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert state to dictionary."""
        return {
            'frequency': self.frequency,
            'gain': self.gain,
            'sample_rate': self.sample_rate,
            'running': self.running,
            'agc_enabled': self.agc_enabled,
            'filter_low': self.filter_low,
            'filter_high': self.filter_high,
            'ptt_enabled': self.ptt_enabled,
            'bias_tee_enabled': self.bias_tee_enabled
        }


class HPSDRProtocolHandler:
    """
    Handler for HPSDR protocol messages.
    
    This class parses incoming HPSDR commands and generates
    appropriate responses. It maintains the device state and
    provides callbacks for state changes.
    
    Attributes:
        device: HermesDevice instance representing this emulator
        state: CurrentControlState instance
        on_frequency_change: Callback when frequency changes
        on_gain_change: Callback when gain changes
        on_sample_rate_change: Callback when sample rate changes
        on_start_rx: Callback when RX starts
        on_stop_rx: Callback when RX stops
    """
    
    def __init__(self, device_name: str = "RTL-Hermes"):
        """
        Initialize the protocol handler.
        
        Args:
            device_name: Name to advertise during discovery.
        """
        self.device = HermesDevice(name=device_name)
        self.state = ControlState()
        
        # Generate random MAC (or use configured one)
        import random
        self.device.mac_address = bytes([random.randint(0, 255) for _ in range(6)])
        
        # Callbacks
        self.on_frequency_change: Optional[Callable[[int], None]] = None
        self.on_gain_change: Optional[Callable[[float], None]] = None
        self.on_sample_rate_change: Optional[Callable[[int], None]] = None
        self.on_start_rx: Optional[Callable[[], None]] = None
        self.on_stop_rx: Optional[Callable[[], None]] = None
        
        logger.info(f"HPSDR protocol handler initialized: {device_name}")
    
    def parse_command(self, data: bytes) -> Optional[bytes]:
        """
        Parse an incoming HPSDR command and generate response.
        
        Args:
            data: Raw command bytes from client.
            
        Returns:
            bytes: Response to send back to client, or None if no response.
        """
        if len(data) < 1:
            return None
        
        command = data[0]
        
        try:
            if command == HermesCommand.DISCOVERY:
                return self._handle_discovery(data)
            elif command == HermesCommand.START_RX:
                return self._handle_start_rx(data)
            elif command == HermesCommand.STOP_RX:
                return self._handle_stop_rx(data)
            elif command == HermesCommand.WRITE_ADDRESS:
                return self._handle_write_address(data)
            elif command == HermesCommand.READ_ADDRESS:
                return self._handle_read_address(data)
            else:
                logger.debug(f"Unknown command: 0x{command:02X}")
                return None
                
        except Exception as e:
            logger.error(f"Error processing command 0x{command:02X}: {e}")
            return None
    
    def _handle_discovery(self, data: bytes) -> bytes:
        """Handle discovery request."""
        logger.info("Discovery request received")
        return self.device.to_discovery_response()
    
    def _handle_start_rx(self, data: bytes) -> Optional[bytes]:
        """Handle start RX command."""
        logger.info("Start RX command received")
        self.state.running = True
        
        if self.on_start_rx:
            try:
                self.on_start_rx()
            except Exception as e:
                logger.error(f"Error in on_start_rx callback: {e}")
        
        # Acknowledge with status
        return struct.pack('>B B', 0x07, 0x00)
    
    def _handle_stop_rx(self, data: bytes) -> Optional[bytes]:
        """Handle stop RX command."""
        logger.info("Stop RX command received")
        self.state.running = False
        
        if self.on_stop_rx:
            try:
                self.on_stop_rx()
            except Exception as e:
                logger.error(f"Error in on_stop_rx callback: {e}")
        
        return struct.pack('>B B', 0x08, 0x00)
    
    def _handle_write_address(self, data: bytes) -> Optional[bytes]:
        """
        Handle write to register/address command.
        
        This is where most configuration happens (frequency, gain, etc.)
        """
        if len(data) < 5:
            return None
        
        # Parse address and value
        # Format: [cmd][addr_high][addr_mid][addr_low][value]
        address = (data[1] << 16) | (data[2] << 8) | data[3]
        value = data[4]
        
        logger.debug(f"Write address 0x{address:04X} = 0x{value:02X}")
        
        # Map addresses to device settings
        # These are approximate mappings based on Hermes-Lite protocol
        if address == 0x0000:  # Frequency control
            # Frequency is typically sent as multiple writes
            # This is simplified - real implementation needs full 28-bit freq
            pass
        elif address == 0x0001:  # Gain control
            gain_db = value * 0.5  # Scale to dB
            self.state.gain = gain_db
            logger.info(f"Gain changed to {gain_db} dB")
            
            if self.on_gain_change:
                try:
                    self.on_gain_change(gain_db)
                except Exception as e:
                    logger.error(f"Error in on_gain_change callback: {e}")
        elif address == 0x0002:  # Sample rate / decimation
            # Map value to sample rate
            rates = {0: 48000, 1: 96000, 2: 192000}
            new_rate = rates.get(value, 48000)
            self.state.sample_rate = new_rate
            
            logger.info(f"Sample rate changed to {new_rate}")
            
            if self.on_sample_rate_change:
                try:
                    self.on_sample_rate_change(new_rate)
                except Exception as e:
                    logger.error(f"Error in on_sample_rate_change callback: {e}")
        elif address == 0x0003:  # Filter control
            pass
        elif address == 0x0004:  # AGC control
            self.state.agc_enabled = (value & 0x01) != 0
            logger.info(f"AGC {'enabled' if self.state.agc_enabled else 'disabled'}")
        
        return struct.pack('>B B B', 0x06, address, value)
    
    def _handle_read_address(self, data: bytes) -> Optional[bytes]:
        """Handle read from register/address command."""
        if len(data) < 4:
            return None
        
        address = (data[1] << 16) | (data[2] << 8) | data[3]
        
        logger.debug(f"Read address 0x{address:04X}")
        
        # Return appropriate value based on address
        value = 0x00  # Default
        
        if address == 0x0001:  # Gain
            value = int(self.state.gain / 0.5)
        elif address == 0x0002:  # Sample rate
            rates = {48000: 0, 96000: 1, 192000: 2}
            value = rates.get(self.state.sample_rate, 0)
        elif address == 0x0004:  # AGC
            value = 0x01 if self.state.agc_enabled else 0x00
        
        return struct.pack('>B B B', 0x05, address, value)
    
    def set_frequency(self, frequency: int) -> None:
        """
        Set the operating frequency.
        
        Args:
            frequency: New frequency in Hz.
        """
        old_freq = self.state.frequency
        self.state.frequency = frequency
        
        logger.info(f"Frequency changed: {old_freq} -> {frequency} Hz")
        
        if self.on_frequency_change:
            try:
                self.on_frequency_change(frequency)
            except Exception as e:
                logger.error(f"Error in on_frequency_change callback: {e}")
    
    def get_state(self) -> Dict[str, Any]:
        """Get current device state."""
        state_dict = self.state.to_dict()
        state_dict['device_name'] = self.device.name
        state_dict['ip_address'] = self.device.ip_address
        state_dict['firmware_version'] = self.device.firmware_version
        return state_dict


class IQPacketBuilder:
    """
    Builds HPSDR-compatible IQ data packets.
    
    Takes formatted IQ bytes and packages them into
    1024-byte packets with appropriate headers.
    """
    
    def __init__(self):
        """Initialize the packet builder."""
        self.sequence_number = 0
        self.buffer = bytearray()
    
    def build_packet(self, iq_data: bytes, 
                     sequence: Optional[int] = None) -> bytes:
        """
        Build a complete HPSDR IQ packet.
        
        Packet structure:
        - Header: 4 bytes [0x05, sequence, 0x00, 0x00]
        - IQ Data: Up to 504 I/Q pairs (1008 bytes)
        - Padding: To reach 1024 bytes total
        
        Args:
            iq_data: Raw IQ data bytes (interleaved I16/Q16).
            sequence: Sequence number (auto-incremented if None).
            
        Returns:
            bytes: Complete 1024-byte packet.
        """
        if sequence is None:
            sequence = self.sequence_number
            self.sequence_number = (self.sequence_number + 1) & 0xFF
        
        # Truncate or pad IQ data to fit packet
        max_iq_bytes = PACKET_SIZE - 4  # Reserve 4 bytes for header
        iq_to_use = iq_data[:max_iq_bytes]
        
        # Build header
        # Header format: [0x05][sequence][0x00][0x00]
        header = struct.pack('>B B B B', 0x05, sequence, 0x00, 0x00)
        
        # Build packet
        packet = header + iq_to_use
        
        # Pad to 1024 bytes
        if len(packet) < PACKET_SIZE:
            packet += b'\x00' * (PACKET_SIZE - len(packet))
        
        return packet[:PACKET_SIZE]
    
    def build_packets(self, iq_data: bytes) -> list:
        """
        Build multiple packets from a large IQ data buffer.
        
        Args:
            iq_data: Large buffer of IQ data bytes.
            
        Returns:
            list: List of 1024-byte packets.
        """
        packets = []
        max_iq_per_packet = PACKET_SIZE - 4
        
        offset = 0
        while offset < len(iq_data):
            chunk = iq_data[offset:offset + max_iq_per_packet]
            packet = self.build_packet(chunk)
            packets.append(packet)
            offset += max_iq_per_packet
        
        return packets
    
    def reset_sequence(self) -> None:
        """Reset the sequence number to 0."""
        self.sequence_number = 0
        logger.debug("Packet sequence reset")


class DiscoveryServer:
    """
    UDP discovery server for HPSDR client detection.
    
    Listens for UDP broadcast discovery requests and
    responds with device information.
    """
    
    def __init__(self, handler: HPSDRProtocolHandler, 
                 interface: str = '0.0.0.0',
                 port: int = HERMES_DISCOVERY_PORT):
        """
        Initialize the discovery server.
        
        Args:
            handler: HPSDRProtocolHandler instance.
            interface: Network interface to bind to.
            port: UDP port for discovery (default: 1024).
        """
        self.handler = handler
        self.interface = interface
        self.port = port
        self.socket: Optional[socket.socket] = None
        self.running = False
        self._thread: Optional[threading.Thread] = None
    
    def start(self) -> bool:
        """
        Start the discovery server.
        
        Returns:
            bool: True if started successfully, False otherwise.
        """
        try:
            # Create UDP socket
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            self.socket.bind((self.interface, self.port))
            self.socket.settimeout(1.0)
            
            self.running = True
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
            
            logger.info(f"Discovery server started on {self.interface}:{self.port}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start discovery server: {e}")
            return False
    
    def stop(self) -> None:
        """Stop the discovery server."""
        self.running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        if self.socket:
            self.socket.close()
            self.socket = None
        logger.info("Discovery server stopped")
    
    def _run(self) -> None:
        """Main discovery server loop."""
        while self.running:
            try:
                data, addr = self.socket.recvfrom(1024)
                
                # Check if this is a discovery request
                if len(data) > 0 and data[0] == HermesCommand.DISCOVERY:
                    logger.info(f"Discovery request from {addr}")
                    
                    # Update device IP
                    self.handler.device.ip_address = addr[0]
                    
                    # Send response
                    response = self.handler.parse_command(data)
                    if response:
                        self.socket.sendto(response, addr)
                        logger.debug(f"Sent discovery response to {addr}")
                        
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    logger.error(f"Discovery server error: {e}")
                break


if __name__ == "__main__":
    # Test the HPSDR protocol handler
    logging.basicConfig(level=logging.INFO)
    
    # Create handler
    handler = HPSDRProtocolHandler(device_name="RTL-Hermes-Test")
    
    # Test discovery
    discovery_req = bytes([0x00])  # Discovery command
    response = handler.parse_command(discovery_req)
    print(f"Discovery response: {response.hex()}")
    
    # Test device info
    print(f"Device: {handler.device.name}")
    print(f"MAC: {handler.device.mac_address.hex()}")
    print(f"State: {handler.get_state()}")
    
    # Test IQ packet building
    builder = IQPacketBuilder()
    test_iq = b'\x00\x01' * 504  # 504 I/Q pairs
    packet = builder.build_packet(test_iq)
    print(f"Packet size: {len(packet)} bytes")
    print(f"Packet header: {packet[:4].hex()}")
