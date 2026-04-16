import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route } from "react-router-dom";

import { DashboardPage } from "./routes/DashboardPage";
import { frontendBootstrap } from "./lib/bootstrap";
import { TripEditorPage } from "./routes/TripEditorPage";

function createQueryClient() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        refetchOnWindowFocus: false,
      },
    },
  });

  const bootstrap = frontendBootstrap();
  if (bootstrap.dashboard) {
    queryClient.setQueryData(["dashboard", bootstrap.dashboard.query], bootstrap.dashboard.data);
  }
  if (bootstrap.bookingPanel) {
    queryClient.setQueryData(
      ["booking-panel", bootstrap.bookingPanel.tripInstanceId],
      bootstrap.bookingPanel.data,
    );
    if (bootstrap.bookingPanel.mode === "edit" && bootstrap.bookingPanel.bookingId) {
      queryClient.setQueryData(
        ["booking-form", bootstrap.bookingPanel.tripInstanceId, bootstrap.bookingPanel.bookingId],
        bootstrap.bookingPanel.data,
      );
    }
  }
  if (bootstrap.trackerPanel) {
    queryClient.setQueryData(
      ["tracker-panel", bootstrap.trackerPanel.tripInstanceId],
      bootstrap.trackerPanel.data,
    );
  }
  if (bootstrap.tripEditor) {
    queryClient.setQueryData(
      ["trip-editor", bootstrap.tripEditor.mode, bootstrap.tripEditor.tripId, bootstrap.tripEditor.query],
      bootstrap.tripEditor.data,
    );
  }
  return queryClient;
}

const queryClient = createQueryClient();

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/app" element={<DashboardPage />} />
          <Route path="/trips/new" element={<TripEditorPage />} />
          <Route path="/trips/:tripId/edit" element={<TripEditorPage />} />
          <Route path="/app/trips/new" element={<TripEditorPage />} />
          <Route path="/app/trips/:tripId/edit" element={<TripEditorPage />} />
          <Route path="*" element={<DashboardPage />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
