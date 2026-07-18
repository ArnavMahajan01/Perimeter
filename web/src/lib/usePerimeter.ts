import { useCallback, useEffect, useRef, useState } from "react";
import { whenReady } from "./api";
import type { AppState, Flash } from "./types";

const POLL_MS = 120;
const FLASH_MS = 550;

/**
 * Polls the pywebview bridge and exposes live app state.
 *
 * Every action re-polls immediately after the backend call resolves instead
 * of waiting for the next scheduled tick — the JS<->Python bridge round trip
 * can lag a poll or two, and without this a click can visually appear to do
 * nothing until the next tick, which reads as "I have to click twice."
 */
export function usePerimeter() {
  const [state, setState] = useState<AppState | null>(null);
  const apiRef = useRef<Awaited<ReturnType<typeof whenReady>> | null>(null);
  const [activeFlashes, setActiveFlashes] = useState<(Flash & { key: number })[]>([]);
  const flashKey = useRef(0);

  const refresh = useCallback(async () => {
    const api = apiRef.current;
    if (!api) return;
    try {
      const next = await api.poll();
      setState(next);
      if (next.flashes.length) {
        const withKeys = next.flashes.map((f) => ({ ...f, key: flashKey.current++ }));
        setActiveFlashes((prev) => [...prev, ...withKeys]);
        withKeys.forEach((f) => {
          setTimeout(() => {
            setActiveFlashes((prev) => prev.filter((x) => x.key !== f.key));
          }, FLASH_MS);
        });
      }
    } catch {
      // window closing
    }
  }, []);

  useEffect(() => {
    let interval: ReturnType<typeof setInterval> | undefined;
    whenReady().then((api) => {
      apiRef.current = api;
      refresh();
      interval = setInterval(refresh, POLL_MS);
    });
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [refresh]);

  /** Fire a backend call, then refresh immediately once it resolves. */
  const act = useCallback(
    async <T,>(fn: (api: NonNullable<typeof apiRef.current>) => Promise<T>): Promise<T | undefined> => {
      const api = apiRef.current;
      if (!api) return undefined;
      const result = await fn(api);
      await refresh();
      return result;
    },
    [refresh],
  );

  return { state, act, activeFlashes };
}

export type Act = ReturnType<typeof usePerimeter>["act"];
export type ActiveFlashes = ReturnType<typeof usePerimeter>["activeFlashes"];
