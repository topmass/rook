// Rook on the Steam Deck: a thin client for Rook, the voice assistant on the PC. The Python backend (main.py) talks
// Rook's phone protocol; this frontend is the Quick Access panel and the toasts. The in-game overlay is a separate
// process (overlay/), started by the backend.
import { addEventListener, definePlugin, removeEventListener } from "@decky/api";
import { staticClasses } from "@decky/ui";
import { RookEvent } from "./api";
import { Icon } from "./icons";
import { Content } from "./panel";
import { store } from "./store";

export default definePlugin(() => {
  // Registered once, at load, so answers and errors reach a toast while the panel is shut.
  const listener = addEventListener<[event: RookEvent]>("rook_event", (event) => store.handle(event));
  store.refresh();

  return {
    name: "Rook",
    titleView: <div className={staticClasses.Title}>Rook</div>,
    content: <Content />,
    icon: <Icon name="rook" size={20} style={{ color: "currentColor" }} />,
    onDismount() {
      removeEventListener("rook_event", listener);
    },
  };
});
