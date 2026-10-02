import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router";
import Projects from "./pages/Projects";
import Evaluation from "./pages/Evaluation";
import NewAnalysis from "./pages/NewAnalysis";
import Plan from "./pages/Plan";
import Review from "./pages/Review";
import Settings from "./pages/Settings";
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/source-serif-4/600.css";
import "@fontsource/noto-sans-devanagari/400.css";
import "@fontsource/noto-sans-devanagari/600.css";
import "./styles.css";

const qc = new QueryClient({ defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false, staleTime: 30_000 } } });

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Projects />} />
          <Route path="/new" element={<NewAnalysis />} />
          <Route path="/runs/:runId" element={<Review />} />
          <Route path="/runs/:runId/plan" element={<Plan />} />
          <Route path="/evaluation" element={<Evaluation />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
