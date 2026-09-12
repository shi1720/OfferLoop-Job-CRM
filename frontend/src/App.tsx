import { Menu, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";

import { useAuth } from "./auth";
import { Wordmark } from "./components/Logo";
import { OnboardingTour } from "./components/OnboardingTour";
import { Sidebar } from "./components/Sidebar";
import { Spinner } from "./components/ui";
import AnalyticsPage from "./pages/AnalyticsPage";
import BoardPage from "./pages/BoardPage";
import ImportPage from "./pages/ImportPage";
import LoginPage from "./pages/LoginPage";
import NudgesPage from "./pages/NudgesPage";
import ProfilePage from "./pages/ProfilePage";
import TodayPage from "./pages/TodayPage";

export default function App() {
  const { user, ready, error } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const location = useLocation();
  useEffect(() => setMenuOpen(false), [location.pathname]); // navigation closes the menu

  if (!ready) {
    return (
      <div className="flex h-screen items-center justify-center gap-3 text-ink-2">
        <Spinner /> Warming up OfferLoop…
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-2 px-6 text-center">
        <p className="font-display text-lg font-semibold">Can't reach the OfferLoop API</p>
        <p className="max-w-md text-sm text-ink-2">{error}</p>
        <p className="text-xs text-ink-3">Start the backend with `make dev` and refresh.</p>
      </div>
    );
  }

  if (!user) return <LoginPage />;

  return (
    <div className="flex h-screen flex-col overflow-hidden md:flex-row">
      {/* Mobile top bar — the sidebar lives behind it as a slide-over */}
      <header className="flex items-center justify-between border-b border-line-soft bg-panel px-4 py-2.5 md:hidden">
        <Wordmark />
        <button
          onClick={() => setMenuOpen(true)}
          aria-label="Open menu"
          className="cursor-pointer rounded-lg p-2 text-ink-2 transition-colors hover:bg-raised hover:text-ink"
        >
          <Menu size={20} />
        </button>
      </header>

      <div className="hidden shrink-0 md:flex">
        <Sidebar />
      </div>

      {menuOpen && (
        <div className="fixed inset-0 z-[60] md:hidden">
          <div className="absolute inset-0 bg-page/60 backdrop-blur-[2px]" onClick={() => setMenuOpen(false)} />
          <div className="animate-rise absolute inset-y-0 left-0 flex">
            <Sidebar onNavigate={() => setMenuOpen(false)} />
          </div>
          <button
            onClick={() => setMenuOpen(false)}
            aria-label="Close menu"
            className="absolute top-3 right-3 cursor-pointer rounded-lg bg-card p-2 text-ink-2"
          >
            <X size={18} />
          </button>
        </div>
      )}

      <main className="min-h-0 flex-1 overflow-y-auto">
        <Routes>
          <Route path="/" element={<TodayPage />} />
          <Route path="/pipeline" element={<BoardPage />} />
          <Route path="/nudges" element={<NudgesPage />} />
          <Route path="/import" element={<ImportPage />} />
          <Route path="/analytics" element={<AnalyticsPage />} />
          <Route path="/profile" element={<ProfilePage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
      <OnboardingTour />
    </div>
  );
}
