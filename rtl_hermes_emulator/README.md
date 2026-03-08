# RTL-SDR to Hermes-Lite Emulator

A software solution that emulates a Hermes-Lite SDR transceiver using an RTL-SDR v3 dongle on a Raspberry Pi, allowing remote reception of ham radio bands over LAN using HPSDR-compatible software.

## Features

- **RTL-SDR Integration**: Full support for RTL-SDR Blog v3 dongles
- **HPSDR Protocol**: Compatible with PowerSDR, Quisk, Thetis, and other HPSDR clients
- **Real-time Streaming**: Low-latency IQ data streaming over TCP/IP
- **Digital Signal Processing**: Decimation, filtering, and AGC
- **Multi-client Support**: Stream to multiple clients simultaneously
- **Remote Control**: Change frequency, gain, and sample rate remotely

## System Requirements

### Hardware
- Raspberry Pi 3/4/Zero 2 W (Pi 4 recommended)
- RTL-SDR Blog v3 dongle
- Ethernet connection (recommended for low latency)
- Optional: TCXO for better frequency stability

### Software
- Raspberry Pi OS (Bullseye or later)
- Python 3.7+
- librtlsdr drivers
- Required Python packages (see requirements.txt)

## Installation

### 1. Install System Dependencies

```bash
sudo apt-get update
sudo apt-get install -y \
    librtlsdr0 \
    librtlsdr-dev \
    libusb-1.0-0-dev \
    python3-pip \
    python3-numpy \
    python3-scipy
```

### 2. Install Python Dependencies

```bash
cd rtl_hermes_emulator
pip install -r requirements.txt
```

### 3. Test RTL-SDR Connection

```bash
python src/main.py --test
```

Expected output:
```
Testing RTL-SDR connection...
Found 1 RTL-SDR device(s)
Device name: Realtek RTL2838UHIDIR
Successfully initialized!
Successfully read 1024 samples
Signal strength: -45.23 dB
```

## Usage

### Basic Usage

Start the emulator with default settings (7 MHz, 20 dB gain):

```bash
cd rtl_hermes_emulator
python src/main.py
```

### Command Line Options

```bash
# Set frequency to 14.2 MHz (20m band)
python src/main.py --frequency 14200000

# Set gain to 35 dB
python src/main.py --gain 35.0

# Use specific RTL-SDR device
python src/main.py --device 0

# Enable verbose logging
python src/main.py --verbose

# Combine options
python src/main.py -f 7150000 -g 25.0 -v
```

### Configuration File

Create a `config.json` file:

```json
{
    "rtlsdr_device": 0,
    "sample_rate": 256000,
    "output_rate": 48000,
    "frequency": 7150000,
    "gain": 25.0,
    "auto_gain": false,
    "network_host": "0.0.0.0",
    "network_port": 1024,
    "device_name": "RTL-Hermes-Shack"
}
```

Then run:

```bash
python src/main.py --config config.json
```

## Connecting HPSDR Clients

### PowerSDR

1. Open PowerSDR
2. Go to Setup → Audio/Codec
3. Select "Network" as the radio type
4. Click "Discover" - your RTL-Hermes should appear
5. Select it and click OK
6. Start receiving

### Quisk

1. Open Quisk
2. Settings → Sound Devices
3. Select "Hermes" as the hardware
4. Enter the Raspberry Pi's IP address
5. Click OK and start

### Thetis

1. Open Thetis
2. Setup → Configure Thetis
3. Select "Hermes-Lite" protocol
4. Click "Scan" for devices
5. Select your RTL-Hermes and connect

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  RTL-SDR    │────▶│  Raspberry   │────▶│   Network   │
│  Dongle     │ USB │  Pi          │ TCP │   LAN       │
│  (RF In)    │     │  (Processing)│     │             │
└─────────────┘     └──────────────┘     └─────────────┘
                                              │
                                              ▼
                                    ┌──────────────┐
                                    │  HPSDR Client│
                                    │  (PowerSDR,  │
                                    │   Quisk)     │
                                    └──────────────┘
```

## Module Overview

### rtlsdr_interface.py
Handles RTL-SDR hardware operations:
- Device detection and initialization
- Sample rate, frequency, and gain control
- IQ sample acquisition
- Error handling and recovery

### signal_processor.py
Digital signal processing:
- Sample rate conversion (decimation)
- FIR filtering with Kaiser window
- Automatic Gain Control (AGC)
- IQ data formatting for HPSDR

### hpsdr_protocol.py
HPSDR protocol emulation:
- UDP discovery server
- Command parsing and response
- IQ packet building
- Device state management

### network_server.py
Network infrastructure:
- TCP data streaming server
- Multi-client support
- Connection management
- Flow control

### main.py
Application integration:
- Component initialization
- Event callbacks
- Main streaming loop
- CLI interface

## Performance Tuning

### Optimal Settings for Raspberry Pi 4

```json
{
    "sample_rate": 256000,
    "output_rate": 48000,
    "auto_gain": true
}
```

### Reduce CPU Usage

- Lower the sample rate (e.g., 256000 → 192000)
- Use lower output rate (48000 instead of 192000)
- Disable AGC if not needed

### Improve Latency

- Use wired Ethernet instead of WiFi
- Reduce buffer sizes in configuration
- Run on Raspberry Pi 4 instead of Pi 3

## Troubleshooting

### No RTL-SDR Devices Found

```bash
# Check USB connection
lsusb | grep RTL

# Check if driver is loaded
lsmod | grep rtl

# Reload driver
sudo modprobe -r rtl2832_sdr
sudo modprobe rtl2832_sdr
```

### High CPU Usage

- Reduce sample rate
- Use fewer decimation stages
- Close other applications

### Connection Issues

```bash
# Check if server is running
netstat -tlnp | grep 1024

# Check firewall
sudo ufw status

# Allow port 1024 if needed
sudo ufw allow 1024
```

### Poor Signal Quality

- Increase gain (--gain 35.0)
- Enable AGC (auto_gain: true)
- Check antenna connection
- Try different frequency

## Limitations

- **Receive Only**: RTL-SDR cannot transmit
- **Dynamic Range**: Lower than dedicated SDR hardware
- **Frequency Stability**: Depends on RTL-SDR oscillator (±50 ppm typical)
- **Maximum Bandwidth**: ~2.4 MHz instantaneous bandwidth

## Development

### Running Tests

```bash
cd rtl_hermes_emulator
python -m pytest tests/
```

### Code Structure

```
rtl_hermes_emulator/
├── src/
│   ├── __init__.py
│   ├── rtlsdr_interface.py
│   ├── signal_processor.py
│   ├── hpsdr_protocol.py
│   ├── network_server.py
│   └── main.py
├── tests/
├── config/
├── docs/
├── requirements.txt
└── README.md
```

## License

GPL-3.0 License

## Contributing

Contributions welcome! Please submit pull requests or open issues for bugs and feature requests.

## Acknowledgments

- RTL-SDR community for excellent drivers
- HPSDR project for the open protocol specification
- Hermes-Lite team for inspiration

## Support

For issues and questions:
1. Check the troubleshooting section
2. Review logs with --verbose flag
3. Open an issue on GitHub
