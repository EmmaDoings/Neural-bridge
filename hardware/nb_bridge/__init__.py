"""Neural Bridge hardware bridge.

Reads EEG from an OpenBCI (or BrainFlow synthetic) board, derives cognitive
metrics and intent, and streams telemetry into the Neural Bridge backend over
the existing device WebSocket.

Run from the `hardware/` directory:

    .venv\\Scripts\\python -m nb_bridge
"""

__version__ = "0.1.0"
