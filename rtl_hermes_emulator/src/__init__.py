"""
RTL-Hermes Emulator Package

This package provides an RTL-SDR to Hermes-Lite emulator,
allowing remote reception of ham radio bands using HPSDR-compatible software.
"""

from .rtlsdr_interface import RtlsdrInterface, test_rtlsdr_connection
from .signal_processor import SignalProcessor, BandpassFilter
from .hpsdr_protocol import (
    HPSDRProtocolHandler,
    IQPacketBuilder,
    DiscoveryServer,
    HermesDevice,
    ControlState
)
from .network_server import DataStreamServer, ControlServer

__version__ = '0.1.0'
__author__ = 'RTL-Hermes Emulator Project'
__license__ = 'GPL-3.0'

__all__ = [
    # RTL-SDR Interface
    'RtlsdrInterface',
    'test_rtlsdr_connection',
    
    # Signal Processing
    'SignalProcessor',
    'BandpassFilter',
    
    # HPSDR Protocol
    'HPSDRProtocolHandler',
    'IQPacketBuilder',
    'DiscoveryServer',
    'HermesDevice',
    'ControlState',
    
    # Network Servers
    'DataStreamServer',
    'ControlServer',
]
