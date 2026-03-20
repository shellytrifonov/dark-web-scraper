"""
Tor Circuit Rotation Utility

Sends a SIGNAL NEWNYM command to the Tor Control Port (9051) to request
a fresh Tor circuit (new exit node / IP address) before each scrape.
This prevents IP-based blocking and improves anonymity.
"""

import logging
import socket
import time

from app.core.config import settings

logger = logging.getLogger(__name__)


def rotate_tor_circuit() -> bool:
    """
    Request a new Tor circuit by sending SIGNAL NEWNYM via the Tor
    Control Port.

    Connects to TOR_PROXY_HOST:TOR_CONTROL_PORT, authenticates with
    TOR_CONTROL_PASSWORD, sends the NEWNYM signal, then sleeps 7 seconds
    to let the new circuit stabilise.

    Returns:
        True if the signal was sent successfully, False otherwise.
    """
    host = settings.TOR_PROXY_HOST
    port = settings.TOR_CONTROL_PORT
    password = settings.TOR_CONTROL_PASSWORD

    try:
        logger.info(f"Rotating Tor circuit via {host}:{port} ...")

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        sock.connect((host, port))

        # Authenticate
        sock.sendall(f'AUTHENTICATE "{password}"\r\n'.encode())
        auth_response = sock.recv(1024).decode().strip()
        if not auth_response.startswith("250"):
            logger.error(f"Tor control authentication failed: {auth_response}")
            sock.close()
            return False

        # Request new identity
        sock.sendall(b"SIGNAL NEWNYM\r\n")
        signal_response = sock.recv(1024).decode().strip()
        if not signal_response.startswith("250"):
            logger.error(f"Tor NEWNYM signal failed: {signal_response}")
            sock.close()
            return False

        sock.close()

        # Mandatory delay to let the new circuit establish
        logger.info("NEWNYM signal sent – waiting 7 s for new circuit ...")
        time.sleep(7)

        logger.info("Tor circuit rotated successfully")
        return True

    except Exception as e:
        logger.warning(f"Tor circuit rotation failed (non-fatal): {e}")
        return False
