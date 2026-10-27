import type { Metadata } from "next";
import HowItWorksPage from "../../how-it-works-page";

export const metadata: Metadata = {
  title: "How It Works — SpanTrace",
  description: "See how SpanTrace moves from repository analysis and controlled execution to evidence-backed diagnosis and verified fixes.",
};

export default function Page() {
  return <HowItWorksPage />;
}
