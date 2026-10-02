import { Link } from "react-router";

/** Floating bottom dock (UI_REFERENCE §3.8). Only destinations that exist are shown. */
export function Dock({ active }: { active: "projects" | "review" }) {
  return (
    <nav className="dock" aria-label="Main">
      <Link to="/" className={active === "projects" ? "on" : ""}>Projects</Link>
      {active === "review" && <a className="on" aria-current="page">Review</a>}
    </nav>
  );
}
