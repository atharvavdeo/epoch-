import { create } from "zustand";

// Shared playhead: the video element is the source of truth for time; anything
// that wants to seek calls seek(ms) and the Player applies it.
type S = {
  currentMs: number;
  seekRequest: { ms: number; n: number } | null;
  selectedIssue: string | null;
  setCurrent: (ms: number) => void;
  seek: (ms: number) => void;
  select: (id: string | null) => void;
};

export const usePlayhead = create<S>((set, get) => ({
  currentMs: 0,
  seekRequest: null,
  selectedIssue: null,
  setCurrent: (ms) => set({ currentMs: ms }),
  seek: (ms) => set({ seekRequest: { ms, n: (get().seekRequest?.n ?? 0) + 1 }, currentMs: ms }),
  select: (id) => set({ selectedIssue: id }),
}));
