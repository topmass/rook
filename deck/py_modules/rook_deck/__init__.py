"""Rook on the Steam Deck: the Decky plugin's backend.

The Deck is a thin client for Rook, which runs on the PC. This package speaks Rook's phone protocol (pairing, the
event stream, typed and spoken requests, speech), records the microphone, plays Rook's speech, watches the controller
for the talk chord, and serves two small HTTP APIs: the Deck agent API that Rook calls (port 47330) and the overlay
feed (127.0.0.1:47331). main.py only wires this package to Decky.

Everything here is the Python standard library, so it runs on Decky's embedded Python 3.11 with nothing installed.
"""

VERSION = "0.1.0"
