"""Rook's Decky plugin backend: the Steam Deck as a thin client for Rook, which runs on the PC.

Decky runs this file in its own Python 3.11 and calls the Plugin methods below from the frontend (src/api.ts). The
work lives in py_modules/rook_deck, which Decky puts on sys.path; this file only hands each callable to it. The
callables and the "rook_event" events are the plugin's contract with the frontend (docs/steamdeck-plan.md in Rook,
"Contracts").
"""

import os
import sys

import decky

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "py_modules"))

from rook_deck.app import App  # noqa: E402


class Plugin:
    app = None

    async def _main(self):
        self.app = App(decky.DECKY_PLUGIN_SETTINGS_DIR, decky.DECKY_PLUGIN_DIR, emit=decky.emit, log=decky.logger,
                       log_dir=decky.DECKY_PLUGIN_LOG_DIR)
        await self.app.start()
        decky.logger.info(f"Rook started as {os.geteuid() == 0 and 'root' or decky.USER}; "
                          f"Deck agent on :{self.app.agent_port}, overlay feed on 127.0.0.1:{self.app.overlay_port}")

    async def _unload(self):
        if self.app is not None:
            await self.app.stop()

    async def _uninstall(self):
        pass

    # The frontend's callables.
    async def get_status(self):
        return await self.app.get_status()

    async def pair(self, server_url, code):
        return await self.app.client.pair(server_url, code)

    async def unpair(self):
        return await self.app.client.unpair()

    async def talk_start(self):
        return await self.app.client.talk_start()

    async def talk_stop(self):
        return await self.app.client.talk_stop()

    async def send_text(self, text):
        return await self.app.client.send_text(text)

    async def stop(self):
        return await self.app.client.stop()

    async def get_history(self):
        return self.app.client.history()

    async def get_deck_token(self):
        return self.app.deck_token()

    async def set_hotkey(self, chord):
        return await self.app.set_hotkey(chord)

    async def answer_card(self, card_id, option):
        return await self.app.client.answer_card(card_id, option)

    async def set_overlay_position(self, anchor):
        return await self.app.set_overlay_position(anchor)

    async def set_addons_dir(self, path):
        return await self.app.set_addons_dir(path)
