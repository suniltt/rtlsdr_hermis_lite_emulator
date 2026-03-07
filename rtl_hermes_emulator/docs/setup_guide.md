# Setup Guide

Step-by-step instructions for setting up the RTL-Hermes Emulator on a Raspberry Pi.

## Prerequisites

- Raspberry Pi 3/4/Zero 2 W with Raspberry Pi OS
- RTL-SDR Blog v3 dongle
- MicroSD card (8GB minimum)
- Network connection (Ethernet recommended)
- Antenna for ham radio bands

## Step 1: Prepare Raspberry Pi

### Install Raspberry Pi OS

1. Download Raspberry Pi Imager from [raspberrypi.com/software](https://www.raspberrypi.com/software/)
2. Flash Raspberry Pi OS (64-bit Bullseye or later) to microSD card
3. Insert card and boot the Pi
4. Complete initial setup (WiFi, locale, etc.)

### Update System

```bash
sudo apt-get update
sudo apt-get upgrade -y
sudo reboot
```

## Step 2: Install RTL-SDR Drivers

### Install Required Packages

```bash
sudo apt-get install -y \
    librtlsdr0 \
    librtlsdr-dev \
    libusb-1.0-0-dev \
    python3-pip \
    python3-numpy \
    python3-scipy \
    git
```

### Verify RTL-SDR Detection

Plug in your RTL-SDR dongle and run:

```bash
lsusb | grep RTL
```

Expected output:
```
Bus 001 Device 004: ID 0bda:2838 Realtek Semiconductor Corp. RTL2838 DVB-T
```

### Test RTL-SDR

```bash
# Check if device is accessible
rtl_test -t
```

Expected output shows "Found 1 device(s)".

## Step 3: Install Python Dependencies

### Create Virtual Environment (Recommended)

```bash
cd ~
python3 -m venv rtl_hermes_env
source rtl_hermes_env/bin/activate
```

### Install Package Dependencies

```bash
cd rtl_hermes_emulator
pip install -r requirements.txt
```

If you encounter errors with scipy:
```bash
# Use pre-built wheels
pip install --only-binary :all: numpy scipy
```

## Step 4: Test Installation

### Run Connection Test

```bash
cd rtl_hermes_emulator
python src/main.py --test
```

Expected output:
```
Testing RTL-SDR connection...
Found 1 RTL-SDR device(s)
Device name: Realtek RTL2838UHIDIR
Successfully initialized!
Successfully read 1024 samples
Signal strength: -XX.XX dB
```

### Troubleshooting

**No devices found:**
```bash
# Check USB permissions
ls -l /dev/bus/usb

# Add user to video group (may help with USB access)
sudo usermod -a -G video $USER

# Reboot and try again
sudo reboot
```

**Permission denied:**
Create udev rule:
```bash
sudo tee /etc/udev/rules.d/20-rtlsdr.rules << 'EOF'
SUBSYSTEM=="usb", ATTR{idVendor}=="0bda", ATTR{idProduct}=="2838", MODE="0666"
EOF

sudo udevadm control --reload-rules
sudo udevadm trigger
```

## Step 5: Configure the Emulator

### Create Configuration File

```bash
cd rtl_hermes_emulator
cp config/default_config.json config.json
```

Edit `config.json`:

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

### Recommended Settings by Band

**HF Bands (40m, 20m, etc.):**
```json
{
    "sample_rate": 256000,
    "output_rate": 48000,
    "gain": 25.0
}
```

**VHF Bands (2m, 70cm):**
```json
{
    "sample_rate": 192000,
    "output_rate": 48000,
    "gain": 30.0
}
```

**Weak Signal Work:**
```json
{
    "sample_rate": 256000,
    "output_rate": 48000,
    "auto_gain": true,
    "gain": 40.0
}
```

## Step 6: Start the Emulator

### Basic Start

```bash
cd rtl_hermes_emulator
python src/main.py
```

### Start with Custom Frequency

```bash
python src/main.py --frequency 14200000 --gain 30.0
```

### Start with Verbose Logging

```bash
python src/main.py --verbose
```

## Step 7: Connect HPSDR Client

### Find Your Pi's IP Address

```bash
hostname -I
```

Note this IP address (e.g., 192.168.1.100).

### PowerSDR Setup

1. Open PowerSDR
2. Go to **Setup** → **Audio/Codec**
3. Under "Radio Type", select **Network**
4. Click **Discover** button
5. Your "RTL-Hermes" should appear in the list
6. Select it and click **OK**
7. Click the **Power** button to start receiving

### Quisk Setup

1. Open Quisk
2. Go to **Settings** → **Sound Devices**
3. Select **Hermes** as hardware type
4. Enter your Pi's IP address
5. Set sample rate to match configuration (48000)
6. Click **OK**
7. Click **Play** button

### Thetis Setup

1. Open Thetis
2. Go to **Setup** → **Configure Thetis**
3. Select **Hermes-Lite** protocol
4. Click **Scan** for devices
5. Select your RTL-Hermes
6. Click **Connect**

## Step 8: Optimize Performance

### Reduce Latency

For better real-time performance:

1. Use Ethernet instead of WiFi
2. In config.json, reduce buffer sizes:
```json
{
    "sample_rate": 192000,
    "output_rate": 48000
}
```

### Improve Stability

Create a systemd service:

```bash
sudo tee /etc/systemd/system/rtl-hermes.service << 'EOF'
[Unit]
Description=RTL-Hermes Emulator
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/rtl_hermes_emulator
ExecStart=/home/pi/rtl_hermes_env/bin/python src/main.py --config config.json
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable rtl-hermes
sudo systemctl start rtl-hermes
```

Check status:
```bash
sudo systemctl status rtl-hermes
```

### Monitor Temperature

RTL-SDR and Pi can get warm:

```bash
# Check Pi temperature
vcgencmd measure_temp

# Check RTL-SDR temperature (if supported)
rtl_test -t
```

If overheating:
- Add heatsinks
- Use a fan
- Reduce sample rate

## Step 9: Testing and Verification

### Test Different Bands

```bash
# 40 meters
python src/main.py --frequency 7150000

# 20 meters
python src/main.py --frequency 14200000

# 15 meters
python src/main.py --frequency 21300000

# 2 meters
python src/main.py --frequency 146520000
```

### Check Signal Quality

1. Tune to a known active frequency
2. Adjust gain for best signal-to-noise
3. Enable AGC if signals vary widely
4. Compare with known SDR receivers

### Network Performance

Monitor network usage:
```bash
# Install nethogs for per-process monitoring
sudo apt-get install nethogs
sudo nethogs
```

Expected bandwidth: ~200-400 KB/s per client at 48 kHz sample rate.

## Troubleshooting

### Common Issues

**Client can't find device:**
- Check firewall settings
- Verify discovery server is running (check logs)
- Ensure port 1024 is not blocked

**Audio is choppy:**
- Reduce sample rate
- Increase network buffer in client software
- Use wired Ethernet

**No audio received:**
- Verify frequency is within amateur band
- Increase gain
- Check antenna connection
- Verify client software is configured correctly

**High CPU usage:**
- Lower sample rate
- Use fewer decimation stages
- Close other applications

### Log Files

Enable detailed logging:
```bash
python src/main.py --verbose 2>&1 | tee emulator.log
```

Review logs for error messages.

## Next Steps

1. Experiment with different bands and modes
2. Join digital mode operations (FT8, etc.)
3. Try remote access from outside your network (requires port forwarding)
4. Consider adding a band-pass filter for better performance
5. Explore automation and scripting possibilities

## Additional Resources

- [RTL-SDR Blog](https://www.rtl-sdr.com/)
- [HPSDR Wiki](http://openhpsdr.org/)
- [PowerSDR Documentation](https://github.com/TAPR/OpenHPSDR-PowerSDR)
- [Ham Radio Band Plans](config/band_plans.json)
