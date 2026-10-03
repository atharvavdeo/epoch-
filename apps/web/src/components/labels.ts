/** Plain-language names for the text model's features (shared by charts, tooltips and the At-this-moment panel). */
export const FEATURE_LABEL: Record<string, string> = {
  setup_before_substance: "Setup before the first point", no_hook_yet: "No clear hook yet", payoff_pending: "Title promise not delivered yet",
  low_novelty: "Little new information", repetition: "Repeated wording", slow_pace: "Slower than usual", fast_pace: "Faster than usual",
  filler_density: "Filler words", dead_air: "Silent gap", cta_or_sponsor: "Mid-video request or sponsor", outro: "Sign-off",
  long_sentences: "Long sentences", open_loop: "An open question keeps interest", concrete: "A concrete example",
  long_static_shot: "One shot held a long time", dense_text_fast_speech: "Dense on-screen text while talking fast",
  flat_low_energy: "Flat, quiet delivery", loudness_drop: "Sudden drop in loudness", fresh_visual_change: "A fresh cut or visual change",
  new_onscreen_text: "New on-screen text", energy_lift: "Livelier delivery",
};
export const featureLabel = (k: string) => FEATURE_LABEL[k] ?? k.replace(/_/g, " ");

/** Which signal a feature is measured from: the reason lanes colour by this. */
export type Modality = "script" | "voice" | "audio" | "visual";
const MOD: Record<string, Modality> = {
  slow_pace: "voice", fast_pace: "voice", filler_density: "voice", flat_low_energy: "voice", energy_lift: "voice",
  dead_air: "audio", loudness_drop: "audio",
  long_static_shot: "visual", fresh_visual_change: "visual", dense_text_fast_speech: "visual", new_onscreen_text: "visual",
};
export const modalityOf = (k: string): Modality => MOD[k] ?? "script";
export const MODALITY_LABEL: Record<Modality, string> = { script: "Script", voice: "Voice", audio: "Audio", visual: "Visuals" };
export const MODALITY_COLOR: Record<Modality, string> = { script: "#121212", voice: "#2457f5", audio: "#8aa4f7", visual: "#a8a39a" };
