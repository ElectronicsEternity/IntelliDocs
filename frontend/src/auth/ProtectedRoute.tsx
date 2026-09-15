import type { PropsWithChildren } from "react";
import { Navigate, useLocation } from "react-router-dom";

import { useAuth } from "./AuthProvider";

export function ProtectedRoute({ children }: PropsWithChildren) {
  const { loading, session } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <main className="centered-page" aria-live="polite">
        <div className="loader" />
        <p>Opening your workspace…</p>
      </main>
    );
  }

  if (!session) return <Navigate to="/auth" replace state={{ from: location }} />;
  return children;
}
