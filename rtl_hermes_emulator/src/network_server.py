"""
Network Server Module

This module provides the TCP/IP server infrastructure for streaming
IQ data to HPSDR clients over the network.

Features:
- Multi-client TCP server
- IQ data streaming with flow control
- Connection management and error handling
- Bandwidth optimization

Author: RTL-Hermes Emulator Project
License: GPL-3.0
"""

import logging
import socket
import threading
import queue
from typing import Optional, Dict, Set, Callable
from dataclasses import dataclass
import time

logger = logging.getLogger(__name__)


@dataclass
class ClientConnection:
    """Represents a connected HPSDR client."""
    address: str
    port: int
    socket: socket.socket
    connected_time: float
    packets_sent: int = 0
    bytes_sent: int = 0
    
    def __str__(self) -> str:
        return f"{self.address}:{self.port}"


class DataStreamServer:
    """
    TCP server for streaming IQ data to HPSDR clients.
    
    This server accepts connections from HPSDR client software
    and streams IQ data packets at the appropriate rate.
    
    Attributes:
        host: Network interface to bind to
        port: TCP port for data streaming
        max_clients: Maximum number of simultaneous clients
        buffer_size: Size of the IQ data buffer
    """
    
    def __init__(self, host: str = '0.0.0.0', port: int = 1024,
                 max_clients: int = 4, buffer_size: int = 100):
        """
        Initialize the data stream server.
        
        Args:
            host: Network interface to bind to (default: all interfaces).
            port: TCP port for data streaming (default: 1024).
            max_clients: Maximum number of simultaneous client connections.
            buffer_size: Number of packets to buffer for each client.
        """
        self.host = host
        self.port = port
        self.max_clients = max_clients
        self.buffer_size = buffer_size
        
        self.server_socket: Optional[socket.socket] = None
        self.clients: Dict[str, ClientConnection] = {}
        self.client_queues: Dict[str, queue.Queue] = {}
        self.client_threads: Dict[str, threading.Thread] = {}
        
        self.running = False
        self._server_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        
        # Callback when client connects/disconnects
        self.on_client_connect: Optional[Callable[[ClientConnection], None]] = None
        self.on_client_disconnect: Optional[Callable[[str], None]] = None
        
        logger.info(f"Data stream server initialized: {host}:{port}")
    
    def start(self) -> bool:
        """
        Start the TCP server.
        
        Returns:
            bool: True if started successfully, False otherwise.
        """
        try:
            # Create TCP socket
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(self.max_clients)
            self.server_socket.settimeout(1.0)
            
            self.running = True
            self._server_thread = threading.Thread(target=self._accept_loop, daemon=True)
            self._server_thread.start()
            
            logger.info(f"Data stream server started on {self.host}:{self.port}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start data stream server: {e}")
            return False
    
    def stop(self) -> None:
        """Stop the server and disconnect all clients."""
        logger.info("Stopping data stream server...")
        
        self.running = False
        
        # Disconnect all clients
        with self._lock:
            client_addresses = list(self.clients.keys())
        
        for addr in client_addresses:
            self._disconnect_client(addr)
        
        # Close server socket
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
            self.server_socket = None
        
        # Wait for server thread
        if self._server_thread:
            self._server_thread.join(timeout=2.0)
        
        logger.info("Data stream server stopped")
    
    def _accept_loop(self) -> None:
        """Main server loop - accept incoming connections."""
        while self.running:
            try:
                client_sock, addr = self.server_socket.accept()
                
                if len(self.clients) >= self.max_clients:
                    logger.warning(f"Max clients ({self.max_clients}) reached, rejecting {addr}")
                    client_sock.close()
                    continue
                
                # Create client connection record
                client = ClientConnection(
                    address=addr[0],
                    port=addr[1],
                    socket=client_sock,
                    connected_time=time.time()
                )
                
                # Add to clients dict
                with self._lock:
                    client_key = f"{addr[0]}:{addr[1]}"
                    self.clients[client_key] = client
                    self.client_queues[client_key] = queue.Queue(maxsize=self.buffer_size)
                
                # Start client handler thread
                thread = threading.Thread(
                    target=self._handle_client,
                    args=(client_key,),
                    daemon=True
                )
                with self._lock:
                    self.client_threads[client_key] = thread
                thread.start()
                
                logger.info(f"Client connected: {client}")
                
                # Notify callback
                if self.on_client_connect:
                    try:
                        self.on_client_connect(client)
                    except Exception as e:
                        logger.error(f"Error in on_client_connect callback: {e}")
                
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    logger.error(f"Accept error: {e}")
                break
    
    def _handle_client(self, client_key: str) -> None:
        """
        Handle communication with a single client.
        
        Args:
            client_key: Unique key identifying the client.
        """
        client = None
        with self._lock:
            client = self.clients.get(client_key)
            client_queue = self.client_queues.get(client_key)
        
        if not client or not client_queue:
            return
        
        client_sock = client.socket
        
        try:
            while self.running and client_key in self.clients:
                try:
                    # Get next packet from queue (with timeout)
                    try:
                        packet = client_queue.get(timeout=0.5)
                    except queue.Empty:
                        continue
                    
                    # Send packet to client
                    client_sock.sendall(packet)
                    
                    # Update statistics
                    with self._lock:
                        if client_key in self.clients:
                            self.clients[client_key].packets_sent += 1
                            self.clients[client_key].bytes_sent += len(packet)
                    
                except socket.error as e:
                    logger.warning(f"Send error to {client}: {e}")
                    break
                except Exception as e:
                    logger.error(f"Client handler error: {e}")
                    break
                    
        finally:
            # Clean up
            self._disconnect_client(client_key)
    
    def _disconnect_client(self, client_key: str) -> None:
        """
        Disconnect a client and clean up resources.
        
        Args:
            client_key: Unique key identifying the client.
        """
        with self._lock:
            client = self.clients.pop(client_key, None)
            client_queue = self.client_queues.pop(client_key, None)
            client_thread = self.client_threads.pop(client_key, None)
        
        if client:
            try:
                client.socket.close()
            except:
                pass
            
            logger.info(f"Client disconnected: {client}")
            
            # Notify callback
            if self.on_client_disconnect:
                try:
                    self.on_client_disconnect(client_key)
                except Exception as e:
                    logger.error(f"Error in on_client_disconnect callback: {e}")
    
    def send_to_all_clients(self, packet: bytes) -> int:
        """
        Send a packet to all connected clients.
        
        Args:
            packet: Binary packet data to send.
            
        Returns:
            int: Number of clients the packet was queued for.
        """
        if not packet:
            return 0
        
        count = 0
        with self._lock:
            for client_key, client_queue in self.client_queues.items():
                try:
                    # Non-blocking put - drop packet if queue full
                    client_queue.put_nowait(packet)
                    count += 1
                except queue.Full:
                    logger.warning(f"Queue full for {client_key}, dropping packet")
        
        return count
    
    def get_connected_clients(self) -> list:
        """
        Get list of currently connected clients.
        
        Returns:
            list: List of ClientConnection objects.
        """
        with self._lock:
            return list(self.clients.values())
    
    def get_statistics(self) -> dict:
        """
        Get server statistics.
        
        Returns:
            dict: Statistics including client count, total packets/bytes sent.
        """
        with self._lock:
            total_packets = sum(c.packets_sent for c in self.clients.values())
            total_bytes = sum(c.bytes_sent for c in self.clients.values())
            
            return {
                'running': self.running,
                'connected_clients': len(self.clients),
                'max_clients': self.max_clients,
                'total_packets_sent': total_packets,
                'total_bytes_sent': total_bytes,
                'clients': [
                    {
                        'address': str(c),
                        'connected_time': c.connected_time,
                        'packets_sent': c.packets_sent,
                        'bytes_sent': c.bytes_sent
                    }
                    for c in self.clients.values()
                ]
            }


class ControlServer:
    """
    TCP server for handling HPSDR control commands.
    
    This server runs on the same port as the data server (1024)
    but handles command/response traffic rather than IQ streaming.
    In practice, this is often multiplexed with the data stream,
    but we separate them here for clarity.
    """
    
    def __init__(self, host: str = '0.0.0.0', port: int = 1024,
                 command_handler: Callable = None):
        """
        Initialize the control server.
        
        Args:
            host: Network interface to bind to.
            port: TCP port for control commands.
            command_handler: Function to process commands.
                           Should take bytes and return bytes (response).
        """
        self.host = host
        self.port = port
        self.command_handler = command_handler
        
        self.server_socket: Optional[socket.socket] = None
        self.running = False
        self._thread: Optional[threading.Thread] = None
        
        logger.info(f"Control server initialized: {host}:{port}")
    
    def start(self) -> bool:
        """Start the control server."""
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5)
            self.server_socket.settimeout(1.0)
            
            self.running = True
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
            
            logger.info(f"Control server started on {self.host}:{self.port}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start control server: {e}")
            return False
    
    def stop(self) -> None:
        """Stop the control server."""
        self.running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        if self.server_socket:
            self.server_socket.close()
            self.server_socket = None
        logger.info("Control server stopped")
    
    def _run(self) -> None:
        """Main control server loop."""
        while self.running:
            try:
                client_sock, addr = self.server_socket.accept()
                client_sock.settimeout(5.0)
                
                # Handle client in same thread (simple implementation)
                # For production, consider threading
                self._handle_client(client_sock, addr)
                
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    logger.error(f"Control server error: {e}")
                break
    
    def _handle_client(self, client_sock: socket.socket, addr: tuple) -> None:
        """Handle a control client connection."""
        logger.info(f"Control connection from {addr}")
        
        try:
            while self.running:
                # Read command
                data = client_sock.recv(1024)
                if not data:
                    break
                
                # Process command
                if self.command_handler:
                    response = self.command_handler(data)
                    if response:
                        client_sock.sendall(response)
                        
        except Exception as e:
            logger.debug(f"Control client error: {e}")
        finally:
            client_sock.close()
            logger.info(f"Control connection closed: {addr}")


if __name__ == "__main__":
    # Test the servers
    logging.basicConfig(level=logging.INFO)
    
    def test_command_handler(data: bytes) -> bytes:
        print(f"Received command: {data.hex()}")
        return b'\x00\x00'  # Simple ACK
    
    # Start servers
    data_server = DataStreamServer()
    control_server = ControlServer(command_handler=test_command_handler)
    
    data_server.start()
    control_server.start()
    
    print("Servers running. Press Ctrl+C to stop.")
    
    try:
        while True:
            time.sleep(1)
            stats = data_server.get_statistics()
            print(f"Clients: {stats['connected_clients']}, "
                  f"Packets: {stats['total_packets_sent']}")
    except KeyboardInterrupt:
        pass
    finally:
        data_server.stop()
        control_server.stop()
