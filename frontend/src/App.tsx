import { Navigate, Route, Routes } from "react-router-dom";

import { useAuth } from "./auth";
import { Sidebar } from "./components/Sidebar";
import { Spinner } from "./components/ui";
import AnalyticsPage from "./pages/AnalyticsPage";
import BoardPage from "./pages/BoardPage";
import ImportPage from "./pages/ImportPage";
import LoginPage from "./pages/LoginPage";
import NudgesPage from "./pages/NudgesPage";
import ProfilePage from "./pages/ProfilePage";

export default function App() {
  const { user, ready, error } = useAuth();

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
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-y-auto">
        <Routes>
          <Route path="/" element={<BoardPage />} />
          <Route path="/nudges" element={<NudgesPage />} />
          <Route path="/import" element={<ImportPage />} />
          <Route path="/analytics" element={<AnalyticsPage />} />
          <Route path="/profile" element={<ProfilePage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}
