import { createContext, useContext, useEffect } from "react";
import type { TabId } from "./detect";

export type IncomingFile = { tab: TabId; name: string; bytes: Uint8Array };

interface RoutedCtx {
  pending: IncomingFile | null;
  clear: () => void;
}

const Ctx = createContext<RoutedCtx>({ pending: null, clear: () => {} });
export const RoutedProvider = Ctx.Provider;

/**
 * A tab calls this with its loader; when a file has been routed to this tab
 * (via the global auto-detect opener) it is loaded automatically and cleared.
 */
export function useIncoming(tabId: TabId, onLoad: (name: string, bytes: Uint8Array) => void): void {
  const { pending, clear } = useContext(Ctx);
  useEffect(() => {
    if (pending && pending.tab === tabId) {
      // Always clear, even if the loader throws, so a bad routed file can't
      // get stuck re-triggering this effect on every render.
      try {
        onLoad(pending.name, pending.bytes);
      } catch (e) {
        console.error("useIncoming load failed", e);
      } finally {
        clear();
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pending, tabId]);
}
