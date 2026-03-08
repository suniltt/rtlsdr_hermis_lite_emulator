# RTL-SDR to Hermes-Lite Emulator Project

## Project Overview

This project emulates a Hermes-Lite SDR transceiver using an RTL-SDR v3 dongle on a Raspberry Pi, allowing remote reception of ham radio bands over LAN using HPSDR-compatible software.

## System Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   RTL-SDR v3    │────▶│  Raspberry Pi    │────▶│   Network LAN   │
│   (RF Input)    │ USB │  (Signal Proc)   │ TCP │  (HPSDR Protocol)│
└─────────────────┘     └──────────────────┘     └─────────────────┘
                                                        │
                                                        ▼
                                              ┌─────────────────┐
                                              │  HPSDR Client   │
                                              │  (PowerSDR,     │
                                              │   Quisk, etc.)  │
                                              └─────────────────┘
```

## Technical Requirements

### Hardware
- Raspberry Pi 3/4/Zero 2 W (Pi 4 recommended for performance)
- RTL-SDR Blog v3 dongle with bias tee capability
- Ethernet connection (wired recommended for low latency)
- Optional: TCXO for better frequency stability

### Software Dependencies
- librtlsdr: RTL-SDR driver library
- libusb-1.0: USB communication
- Python 3.7+ or C++ with proper libraries
- HPSDR protocol knowledge

## HPSDR Protocol Overview

The Hermes-Lite uses a specific TCP/IP protocol:
- **Discovery**: UDP broadcast on port 1024
- **Control**: TCP connection on port 1024
- **IQ Data**: TCP connection on port 1024 (multiplexed)
- **Packet Structure**: 1024-byte packets with header + IQ samples

### Key Protocol Elements
1. Discovery beacon (UDP)
2. Control commands (frequency, gain, filter settings)
3. IQ sample streaming (16-bit I/Q pairs)
4. Status reporting

## Implementation Plan

### Phase 1: RTL-SDR Interface Layer
- Initialize RTL-SDR dongle
- Configure sample rate, frequency, gain
- Read IQ samples from device
- Handle device errors and reconnection

### Phase 2: Signal Processing Layer
- Sample rate conversion (RTL-SDR native to HPSDR standard)
- Digital filtering and decimation
- Gain control and AGC
- Frequency translation if needed

### Phase 3: HPSDR Protocol Emulation
- Implement discovery beacon
- Parse control commands
- Format IQ data packets
- Manage client connections

### Phase 4: Network Server
- Multi-client support
- Connection management
- Bandwidth optimization
- Error handling and recovery

### Phase 5: Configuration & Control
- Web interface or configuration file
- Remote parameter adjustment
- Status monitoring
- Logging and diagnostics

## Directory Structure

```
rtl_hermes_emulator/
├── src/
│   ├── __init__.py
│   ├── rtlsdr_interface.py      # RTL-SDR hardware interface
│   ├── signal_processor.py       # DSP operations
│   ├── hpsdr_protocol.py         # HPSDR protocol implementation
│   ├── network_server.py         # TCP/UDP server
│   ├── config_manager.py         # Configuration handling
│   └── main.py                   # Application entry point
├── tests/
│   ├── test_rtlsdr.py
│   ├── test_protocol.py
│   └── test_integration.py
├── config/
│   ├── default_config.json
│   └── band_plans.json
├── docs/
│   ├── api_reference.md
│   ├── setup_guide.md
│   └── protocol_spec.md
├── requirements.txt
├── setup.py
└── README.md
```

## Performance Considerations

1. **Sample Rate**: RTL-SDR max ~2.4 MSPS, HPSDR typically 48-192 kHz
2. **CPU Usage**: Decimation and filtering are CPU-intensive
3. **Network Latency**: Target <50ms for responsive operation
4. **Buffer Management**: Prevent underruns/overruns
5. **Thermal Throttling**: Monitor Pi temperature under load

## Limitations vs Real Hermes-Lite

- **Receive Only**: RTL-SDR cannot transmit
- **Dynamic Range**: Lower than dedicated SDR hardware
- **Frequency Stability**: Depends on RTL-SDR oscillator
- **Bandwidth**: Limited by USB 2.0 and Pi processing
- **No Advanced Features**: No ATU, no PA control, limited filtering

## Next Steps

1. Install dependencies on Raspberry Pi
2. Test RTL-SDR basic functionality
3. Implement core modules incrementally
4. Test with HPSDR software (PowerSDR, Quisk)
5. Optimize performance and stability
6. Add configuration interface
