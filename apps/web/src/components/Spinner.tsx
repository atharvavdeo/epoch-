import { useIsFetching, useIsMutating } from "@tanstack/react-query";
import type { ReactNode } from "react";

/** Small inline spinner for buttons whose action is in flight. */
export function Spinner() {
  return <span className="spinner" aria-hidden />;
}

/** Button label that swaps in a spinner while `busy`. */
export function Busy({ busy, children }: { busy: boolean; children: ReactNode }) {
  return <>{busy && <Spinner />}{children}</>;
}

/** Thin blue bar at the top of the viewport while any fetch or mutation runs.
 *  Background polling of pipeline status is excluded so the bar does not flash every few seconds. */
export function TopProgress() {
  const fetching = useIsFetching({ predicate: (q) => q.queryKey[0] !== "pipeline" || q.state.data === undefined });
  const mutating = useIsMutating();
  const on = fetching + mutating > 0;
  return <div className={`topbar ${on ? "on" : ""}`} role="progressbar" aria-hidden={!on} aria-label="Loading" />;
}

/** Shimmer placeholder blocks used instead of bare "Loading…" text. */
export function Skeleton({ w = "100%", h = 14, r }: { w?: number | string; h?: number; r?: number }) {
  return <span className="skel" style={{ width: w, height: h, borderRadius: r }} />;
}

/** A few stacked skeleton lines for a loading card. */
export function SkeletonBlock({ lines = 3, chart }: { lines?: number; chart?: boolean }) {
  return <div className="skel-block" aria-busy="true" aria-label="Loading">
    {chart && <Skeleton h={180} r={14} />}
    {Array.from({ length: lines }, (_, i) => <Skeleton key={i} w={`${92 - i * 14}%`} h={14} />)}
  </div>;
}
