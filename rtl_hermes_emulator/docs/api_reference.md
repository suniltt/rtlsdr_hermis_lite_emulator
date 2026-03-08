# API Reference Documentation

Complete API documentation for the RTL-Hermes Emulator.

## Table of Contents

1. [RtlsdrInterface](#rtlsdrinterface)
2. [SignalProcessor](#signalprocessor)
3. [HPSDRProtocolHandler](#hpsdrprotocolhandler)
4. [DataStreamServer](#datastreamserver)
5. [RTLHermesEmulator](#rtlhermesemulator)

---

## RtlsdrInterface

**Module**: `rtlsdr_interface`

Interface class for RTL-SDR hardware operations.

### Constructor

```python
RtlsdrInterface(device_index: int = 0)
```

**Parameters:**
- `device_index` (int): Index of the RTL-SDR device if multiple are connected.

### Methods

#### detect_devices() → int

Detect the number of RTL-SDR devices connected.

**Returns:** Number of devices detected.

**Example:**
```python
iface = RtlsdrInterface()
count = iface.detect_devices()
print(f"Found {count} devices")
```

#### initialize(sample_rate, center_freq, gain, auto_gain) → bool

Initialize and configure the RTL-SDR device.

**Parameters:**
- `sample_rate` (int): Sample rate in samples per second (default: 256000)
- `center_freq` (int): Center frequency in Hz (default: 7000000)
- `gain` (float, optional): Manual gain in dB
- `auto_gain` (bool): Enable automatic gain control

**Returns:** True if successful.

**Example:**
```python
success = iface.initialize(
    sample_rate=256000,
    center_freq=14200000,
    gain=35.0,
    auto_gain=False
)
```

#### set_center_frequency(frequency: int) → bool

Set the center frequency.

**Parameters:**
- `frequency` (int): Frequency in Hz

**Example:**
```python
iface.set_center_frequency(7150000)  # 7.150 MHz
```

#### set_manual_gain(gain: float) → bool

Set manual gain.

**Parameters:**
- `gain` (float): Gain in dB (0.0 to 49.6)

#### read_samples(num_samples: int) → numpy.ndarray

Read IQ samples from the device.

**Parameters:**
- `num_samples` (int): Number of samples to read

**Returns:** Complex numpy array of IQ samples.

#### get_signal_strength(num_samples: int) → float

Measure current signal strength.

**Returns:** Signal strength in dB (relative).

#### close()

Close the device and release resources.

---

## SignalProcessor

**Module**: `signal_processor`

Digital signal processor for RTL-SDR to HPSDR conversion.

### Constructor

```python
SignalProcessor(input_rate: int = 256000, output_rate: int = 48000)
```

**Parameters:**
- `input_rate` (int): Input sample rate from RTL-SDR
- `output_rate` (int): Output sample rate for HPSDR (48000, 96000, or 192000)

### Methods

#### process_samples(samples: np.ndarray) → np.ndarray

Process a block of input samples through decimation and filtering.

**Parameters:**
- `samples` (np.ndarray): Input complex IQ samples

**Returns:** Decimated and filtered complex IQ samples.

**Example:**
```python
proc = SignalProcessor(256000, 48000)
rtl_samples = rtlsdr.read_samples(2560)
output = proc.process_samples(rtl_samples)
```

#### format_iq_for_hpsdr(samples: np.ndarray) → bytes

Format IQ samples for HPSDR protocol transmission.

**Parameters:**
- `samples` (np.ndarray): Complex IQ samples (normalized -1.0 to 1.0)

**Returns:** Binary data with interleaved I16/Q16 samples.

#### enable_agc(enable, target_level, attack, decay)

Configure automatic gain control.

**Parameters:**
- `enable` (bool): Enable AGC
- `target_level` (float): Target RMS level (0.0 to 1.0)
- `attack` (float): Attack rate
- `decay` (float): Decay rate

#### get_statistics() → dict

Get processing statistics.

**Returns:** Dictionary with keys:
- `samples_processed`: Total samples processed
- `clips_detected`: Number of clipping events
- `agc_gain`: Current AGC gain
- `buffer_size`: Current buffer fill level

---

## HPSDRProtocolHandler

**Module**: `hpsdr_protocol`

Handler for HPSDR protocol messages.

### Constructor

```python
HPSDRProtocolHandler(device_name: str = "RTL-Hermes")
```

**Parameters:**
- `device_name` (str): Name to advertise during discovery

### Properties

#### on_frequency_change : Callable[[int], None]

Callback when frequency changes.

#### on_gain_change : Callable[[float], None]

Callback when gain changes.

#### on_start_rx : Callable[[], None]

Callback when RX starts.

#### on_stop_rx : Callable[[], None]

Callback when RX stops.

### Methods

#### parse_command(data: bytes) → Optional[bytes]

Parse an incoming HPSDR command and generate response.

**Parameters:**
- `data` (bytes): Raw command bytes from client

**Returns:** Response bytes or None.

#### set_frequency(frequency: int)

Set the operating frequency.

**Parameters:**
- `frequency` (int): Frequency in Hz

#### get_state() → dict

Get current device state.

**Returns:** Dictionary with all state parameters.

---

## IQPacketBuilder

**Module**: `hpsdr_protocol`

Builds HPSDR-compatible IQ data packets.

### Methods

#### build_packet(iq_data: bytes, sequence: int = None) → bytes

Build a complete HPSDR IQ packet.

**Parameters:**
- `iq_data` (bytes): Raw IQ data bytes (interleaved I16/Q16)
- `sequence` (int, optional): Sequence number (auto-incremented if None)

**Returns:** Complete 1024-byte packet.

#### reset_sequence()

Reset the sequence number to 0.

---

## DataStreamServer

**Module**: `network_server`

TCP server for streaming IQ data to HPSDR clients.

### Constructor

```python
DataStreamServer(host='0.0.0.0', port=1024, max_clients=4, buffer_size=100)
```

**Parameters:**
- `host` (str): Network interface to bind to
- `port` (int): TCP port for data streaming
- `max_clients` (int): Maximum simultaneous clients
- `buffer_size` (int): Packet buffer size per client

### Methods

#### start() → bool

Start the TCP server.

**Returns:** True if successful.

#### stop()

Stop the server and disconnect all clients.

#### send_to_all_clients(packet: bytes) → int

Send a packet to all connected clients.

**Parameters:**
- `packet` (bytes): Binary packet data

**Returns:** Number of clients the packet was queued for.

#### get_connected_clients() → list

Get list of currently connected clients.

#### get_statistics() → dict

Get server statistics.

**Returns:** Dictionary with:
- `running`: Server running status
- `connected_clients`: Number of active clients
- `total_packets_sent`: Total packets transmitted
- `total_bytes_sent`: Total bytes transmitted

---

## DiscoveryServer

**Module**: `hpsdr_protocol`

UDP discovery server for HPSDR client detection.

### Constructor

```python
DiscoveryServer(handler, interface='0.0.0.0', port=1024)
```

**Parameters:**
- `handler` (HPSDRProtocolHandler): Protocol handler instance
- `interface` (str): Network interface
- `port` (int): UDP port (default: 1024)

### Methods

#### start() → bool

Start the discovery server.

#### stop()

Stop the discovery server.

---

## RTLHermesEmulator

**Module**: `main`

Main application class integrating all components.

### Constructor

```python
RTLHermesEmulator(config: Dict[str, Any])
```

**Configuration Keys:**
- `rtlsdr_device` (int): Device index
- `sample_rate` (int): RTL-SDR sample rate
- `output_rate` (int): HPSDR output rate
- `frequency` (int): Initial frequency in Hz
- `gain` (float): Initial gain in dB
- `auto_gain` (bool): Enable AGC
- `network_host` (str): Network interface
- `network_port` (int): Network port
- `device_name` (str): Device name for discovery

### Methods

#### start() → bool

Start all components.

#### stop()

Stop all components.

#### run_forever()

Run until interrupted (Ctrl+C).

#### get_status() → dict

Get comprehensive system status.

---

## Error Handling

All methods that can fail return appropriate error indicators:
- Boolean returns: True for success, False for failure
- None returns: Indicates failure or no data
- Exceptions: Raised for critical errors

### Common Exceptions

- `RuntimeError`: Device initialization failures
- `ValueError`: Invalid parameter values
- `IOError`: Hardware communication errors

### Best Practices

```python
# Always use try-finally for resource cleanup
iface = RtlsdrInterface()
try:
    iface.initialize()
    # ... use device ...
finally:
    iface.close()

# Check return values
if not processor:
    logger.error("Failed to initialize processor")
    return

# Handle exceptions gracefully
try:
    samples = iface.read_samples(1024)
except Exception as e:
    logger.error(f"Sample read failed: {e}")
    samples = None
```

---

## Threading Considerations

The emulator uses multiple threads:
- Main thread: Application control
- Streaming thread: IQ data acquisition and processing
- Server threads: Network I/O
- Client threads: Per-client data delivery

### Thread Safety

- All callback functions should be thread-safe
- Don't block in callbacks
- Use queues for inter-thread communication

### Example Callback

```python
def safe_frequency_callback(freq: int):
    # Queue the change instead of doing it directly
    frequency_queue.put(freq)

protocol_handler.on_frequency_change = safe_frequency_callback
```

---

## Performance Tips

1. **Minimize allocations**: Reuse buffers where possible
2. **Batch processing**: Process samples in large blocks
3. **Avoid blocking I/O**: Use async patterns for network
4. **Monitor CPU usage**: Adjust sample rates accordingly
5. **Use appropriate buffer sizes**: Balance latency vs stability
