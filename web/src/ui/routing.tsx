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
export function useIncoming(tabId: string, onLoad: (name: string, bytes: Uint8Array) => void): void {
  const { pending, clear } = useContext(Ctx);
  useEffect(() => {
    if (pending && pending.tab === tabId) {
      onLoad(pending.name, pending.bytes);
      clear();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pending, tabId]);
}
