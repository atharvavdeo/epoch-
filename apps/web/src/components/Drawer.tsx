import { useEffect, type ReactNode } from "react";
import { IconClose } from "./Icons";

/** Right-hand drawer for evidence, the full findings list and the assistant. One open at a time; Esc closes. */
export function Drawer({ title, kicker, onClose, children, wide }: {
  title: string; kicker?: string; onClose: () => void; children: ReactNode; wide?: boolean;
}) {
  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  return (
    <>
    <div className="scrim" onClick={onClose} />
    <aside className={`drawer ${wide ? "wide" : ""}`} role="dialog" aria-label={title}>
      <div className="drawer-head">
        <div>{kicker && <div className="kicker">{kicker}</div>}<b>{title}</b></div>
        <button className="icon-btn" aria-label={`Close ${title}`} title="Close (Esc)" onClick={onClose}><IconClose /></button>
      </div>
      <div className="drawer-body">{children}</div>
    </aside></>
  );
}
