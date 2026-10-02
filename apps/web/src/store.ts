import { create } from "zustand";
import type { Interval } from "./api";

// One shared selection model for the whole Review screen. The video element is the source of truth for
// time; anything that wants to move it calls seek(ms) / focus(interval) and the Player applies it.
// A click on a word, shot, finding, chart bin or chat citation goes through focus(), so every panel
// highlights the same interval.
type S = {
  currentMs: number;
  seekRequest: { ms: number; n: number } | null;
  selectedIssue: string | null;
  selection: Interval | null;
  setCurrent: (ms: number) => void;
  seek: (ms: number) => void;
  select: (id: string | null) => void;
  focus: (iv: Interval, issueId?: string | null) => void;
  clearSelection: () => void;
};

export const usePlayhead = create<S>((set, get) => ({
  currentMs: 0,
  seekRequest: null,
  selectedIssue: null,
  selection: null,
  setCurrent: (ms) => set({ currentMs: ms }),
  seek: (ms) => set({ seekRequest: { ms, n: (get().seekRequest?.n ?? 0) + 1 }, currentMs: ms }),
  select: (id) => set({ selectedIssue: id }),
  focus: (iv, issueId) => set({
    selection: iv, seekRequest: { ms: iv.start_ms, n: (get().seekRequest?.n ?? 0) + 1 }, currentMs: iv.start_ms,
    ...(issueId !== undefined ? { selectedIssue: issueId } : {}),
  }),
  clearSelection: () => set({ selection: null }),
}));

export const overlaps = (a: Interval, b: Interval) => a.start_ms < b.end_ms && b.start_ms < a.end_ms;
