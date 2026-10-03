import { useEffect, useRef } from "react";
import { useLocation } from "react-router";
import { driver, type Driver } from "driver.js";
import "driver.js/dist/driver.css";
import "./walkthrough.css";

type Stop = { title: string; text: string; selector?: string; heading?: string; tab?: string; output?: string; disclosure?: string; formStep?: string };
const stop = (title: string, text: string, extra: Omit<Stop, "title" | "text"> = {}): Stop => ({ title, text, ...extra });
const chart = (tab: string, heading: string, text: string) => stop(heading, text, { tab, heading });
const headingElement = (title: string) => Array.from(document.querySelectorAll("h2,h3,h4,summary")).find(e => e.textContent?.trim().startsWith(title));
function target(s: Stop): Element | undefined { return (s.heading ? headingElement(s.heading)?.closest("section,details,.card") : s.selector ? document.querySelector(s.selector) : undefined) ?? undefined; }
function stops(path: string): Stop[] {
  const nav = stop("Explore the whole workspace", "Each page has its own walkthrough. Open Projects, Review, Edit plan, Evaluation, Settings or New, then choose Start walkthrough again. This tour submits no forms, requests no cloud opinions and edits no source.", { selector: ".dock" });
  if (path.endsWith("/plan")) return [stop("Edit plan", "Accepted decisions form a reviewable plan. Your original file remains intact.", { selector: ".summary" }), stop("Queue", "Inspect accepted cuts, rewrites, review states and overlap conflicts before export.", { heading: "Queue" }), stop("Compare", "Cut comparisons use an assumed audience. Compare watch seconds as well as percentage viewed; shortening the denominator can raise percentage.", { heading: "Compare" }), stop("Reanalyse the edited source", "Export the plan, edit externally, and analyse the edited file as a new run for a source-grounded comparison.", { heading: "Reanalysed video" }), nav];
  if (path.startsWith("/runs/")) {
    const result = [stop("Review this run", "Title, duration, run selector and missing-coverage disclosures identify this immutable analysis.", { selector: ".rv-head" }), stop("Summary estimates", "Viewed percentage and watch time are uncalibrated scenarios, not measured audience analytics. Findings and title payoff link to evidence.", { selector: ".kpis" }), stop("Source and selected moment", "Play the media or inspect the script. The neighbouring moment card follows the shared playhead.", { selector: ".ws2" }), stop("Shared timeline", "Chapters, findings, risk and coverage tracks share time coordinates. Click an interval to inspect it across charts.", { selector: ".tl-card" }),
      chart("overview", "Viewers still watching", "Compare feature-adjusted survival with the assumed baseline. The shaded range is assumption sensitivity, not a confidence interval."),
      chart("overview", "Viewers leaving per second", "Departure rate fluctuates locally although survival cannot rise. These undulations come from model inputs."),
      chart("overview", "Why — transcript risk", "Five-second grouped rule features explain candidate pressure. Unknown coverage does not mean no risk."),
      chart("overview", "Watch time", "Cumulative watch time integrates survival over actual bin durations."),
      chart("overview", "Sections", "Chapters, promises and structural markers help interpret a dip in context."),
      chart("overview", "Look at these first", "Prioritised findings connect concern, counter-explanation, evidence and a suggested review action."),
      chart("retention", "Retention breakdown", "The dedicated view separates survival, departure pressure, attribution and priority windows."),
      chart("retention", "Departure pressure over time", "Hazard divided by baseline hazard reveals changing pressure. One means baseline; above one means greater departure pressure."),
      chart("retention", "Selected moment", "Seek to inspect remaining viewers, conditional departures, attributed causes and protective candidates."),
      chart("retention", "Priority drop moments", "Ranked windows use excess departures and actual time bounds. Click a timestamp to inspect the source."),
      chart("retention", "Viewers leaving per second", "Departure rate has a different denominator from the remaining-viewer percentage."),
      chart("retention", "Watch time", "Integration includes the final fractional second. Watch seconds and percentage tell different stories."),
      stop("Assumptions and rules", "Inspect anchors and rule attribution. Recompute only after deliberately acknowledging the assumed audience; the tour never submits this form.", { tab: "retention", disclosure: "How this is calculated", heading: "How this is calculated" }),
      chart("text", "Transcript risk", "Text mechanisms are candidate concerns requiring contextual editorial review."),
      chart("text", "Findings", "Inspect quotes, intervals, counter-explanations and review controls before accepting an action."),
      chart("text", "Words per minute", "Transcript density depends on timing provenance. Script timings are estimates."),
      chart("text", "New ideas", "New-term density describes information load, not whether unfamiliar words are bad."),
      stop("Questions and ideas", "Inspect question, idea and promise relations. Lexical relationships require contextual review.", { tab: "text", disclosure: "Questions and ideas", heading: "Questions and ideas" }),
      stop("Question → answer", "Later shared wording is a pointer to inspect, not proof that a promise was paid off.", {tab:"text",disclosure:"Questions and ideas",heading:"Question → answer"}),
      stop("Abstract stretches", "Long passages without a concrete example, number or named thing can deserve review. Check source context before acting.", {tab:"text",disclosure:"Questions and ideas",heading:"Abstract stretches"}),
      stop("Explained after first use", "Term dependencies link first usage to a later explanation and its timestamp.", {tab:"text",disclosure:"Questions and ideas",heading:"Explained after first use"}),
      stop("New ideas per minute", "Minute bars show new content words relative to this transcript. The first minute is new by definition and is not flagged.", {tab:"text",disclosure:"Questions and ideas",heading:"New ideas per minute"}),
      stop("Rhythm", "Sentence-length variation and section durations describe narrative rhythm; they are editorial clues rather than measured boredom.", {tab:"text",disclosure:"Questions and ideas",heading:"Rhythm"}),
      stop("Full transcript", "Read timestamped source text and available aligned words. Missing word timing is disclosed.", { tab: "text", disclosure: "Full transcript", heading: "Full transcript" }),
      stop("Jev second opinion", "Typed decisions route uncertain passages to review. Shortening requires deterministic evidence validation. This tour makes no cloud requests.", { tab: "text", disclosure: "Second opinion on a passage", heading: "Second opinion on a passage" })];
    if (document.querySelector('[data-tour-tab="voice"]')) result.push(chart("voice", "Speaking rate", "Aligned word rate is measured in temporal windows."), chart("voice", "Pitch", "Estimated fundamental frequency describes delivery, not emotion or identity."), chart("voice", "Pitch variation", "Within-window pitch spread helps inspect delivery. Music and unvoiced speech can limit it."), chart("voice", "Voiced share", "The share of frames passing a voicing criterion is not speech recognition accuracy."), chart("audio", "Level", "RMS level in dBFS describes short-window signal energy."), chart("audio", "Loudness", "Short-term LUFS and integrated loudness describe perceived level; peaks and clipping provide separate checks."), chart("audio", "Silent gaps", "Click a measured gap and listen before deciding whether to edit it."));
    result.push(...([['files', 'Exported files', 'Download traceable artifacts and reports.'], ['shots', 'Shots', 'Inspect available shot evidence. Missing visual AI coverage stays visible.'], ['ocr', 'On-screen text', 'Inspect sampled-frame OCR and timestamps. Empty or unavailable OCR is disclosed.'], ['run', 'Run details', 'Inspect stage status, coverage, models, provenance and older scoring views.']] as const).map(([output,title,text]) => stop(title,text,{tab:"outputs",output,selector:".tab-body"})), stop("Older track scoring", "This disclosed chart uses the older narrative scoring system. Do not combine its scale with the current retention scenario.", {tab:"outputs",output:"run",disclosure:"Risk by track",heading:"Risk by track"}), stop("Older findings scenario", "The earlier findings-based estimate remains separately labelled for comparison and provenance; it is also uncalibrated.", {tab:"outputs",output:"run",disclosure:"Findings-based scenario",heading:"Findings-based scenario"}), stop("Ask and edit plan", "Ask retrieves grounded evidence; the edit plan collects accepted decisions. This tour triggers neither action.", { selector: ".rv-actions" }), nav);
    return result;
  }
  if (path === "/new") return [stop("Three safe steps", "Goal defines context, Upload chooses a source, and Processing reports the serial job. This tour never fills or submits your form.", { selector: ".stepper" }), stop("Title and context", "Use the exact title, category, language and optional audience so payoff and language processing have context.", { selector: ".step-card" }), stop("Source options", "After entering a title, Continue opens video/audio upload or pasted script. Packages can also be imported. Script timing is estimated unless timestamp cues are supplied.", { selector: ".step-card", formStep: "Upload" }), stop("Progress and recovery", "Processing shows stages, progress and bounded logs. Package validation precedes review. Failed jobs remain visible and can be retried.", { selector: ".stepper" }), nav];
  if (path === "/evaluation") return [stop("Evidence limits", "Read the validation disclosure before treating any number as accuracy.", { heading: "Not validated yet" }), stop("Reviewer decisions", "Counts by finding type describe review activity, not a labelled accuracy benchmark.", { heading: "Reviewer decisions by finding type" }), stop("Runs and coverage", "Inspect analysed runs and available evidence; missing stages are part of the result.", { heading: "Videos analysed" }), nav];
  if (path === "/settings") return [stop("Creator defaults", "Language, category and audience pre-fill new analyses. Saving changes local preferences.", { heading: "Creator defaults" }), stop("Connections and storage", "Inspect storage and optional service configuration. Credentials remain in server environment configuration.", { heading: "Connections & storage" }), nav];
  return [stop("Project library", "Cards show title, language, coverage and status. Uncalibrated percentages are scenarios.", { selector: ".pj-card" }), stop("Find a project", "Search, sort and filter without changing sources.", { selector: ".tb-tools" }), stop("Start an analysis", "Choose New for video, audio, script or an exported package. Local processing requires the backend; the hosted showcase uses seeded examples.", { selector: 'a[href="/new"]' }), nav];
}
export function Walkthrough() {
  const { pathname } = useLocation();
  const active = useRef<Driver | null>(null), generation = useRef(0);
  useEffect(() => { generation.current++; active.current?.destroy(); active.current = null; }, [pathname]);
  useEffect(() => () => { generation.current++; active.current?.destroy(); }, []);
  const start = async () => {
    active.current?.destroy();
    const specs = stops(pathname), origin = document.activeElement as HTMLElement | null, token = ++generation.current;
    const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
    let busy = false;
    const tour = driver({ animate: !reduced, smoothScroll: !reduced, allowKeyboardControl: true, showProgress: true, popoverClass: "epoch-tour", nextBtnText: "Next", prevBtnText: "Back", doneBtnText: "Finish",
      onNextClick: () => { const n = (tour.getActiveIndex() ?? 0) + 1; if (n >= specs.length) tour.destroy(); else void go(n); },
      onPrevClick: () => { void go(Math.max(0, (tour.getActiveIndex() ?? 0) - 1)); },
      onDestroyed: () => { generation.current++; origin?.focus(); active.current = null; },
      steps: specs.map(s => ({ element: () => target(s) ?? document.querySelector(".tab-body,.shell,.page-projects") ?? document.body, popover: { title: s.title, description: `${s.text} If no data exists for this view, its availability message is the result.`, side: "bottom" } })) });
    active.current = tour;
    async function go(index: number) {
      if (busy) return; busy = true;
      const s = specs[index];
      if (s.formStep) {
        const control = Array.from(document.querySelectorAll<HTMLButtonElement>(".stepper button")).find(e => e.textContent?.includes(s.formStep!));
        if (control && !control.disabled) control.click();
      }
      if (s.tab) (document.querySelector(`[data-tour-tab="${s.tab}"]`) as HTMLElement | null)?.click();
      await new Promise(resolve => setTimeout(resolve, 80));
      if (s.output) (document.querySelector(`[data-tour-output="${s.output}"]`) as HTMLElement | null)?.click();
      for (let n = 0; n < 24 && !target(s) && token === generation.current; n++) await new Promise(resolve => setTimeout(resolve, 80));
      if (s.disclosure) { const d = headingElement(s.disclosure)?.closest("details"); if (d) d.open = true; }
      busy = false;
      if (token === generation.current) tour.drive(index);
    }
    await go(0);
  };
  return <button className="walkthrough-start" onClick={() => void start()} aria-label="Start walkthrough of this page">Start walkthrough</button>;
}
