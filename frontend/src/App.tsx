import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route } from "react-router-dom";

import { ConfirmProvider } from "./components/ConfirmProvider";
import { ToastProvider } from "./components/ToastProvider";
import { DashboardPage } from "./routes/DashboardPage";
import { frontendBootstrap } from "./lib/bootstrap";
import {
  bookingFormQueryKey,
  bookingPanelQueryKey,
  dashboardQueryKey,
  trackerPanelQueryKey,
  tripEditorQueryKey,
} from "./lib/queryKeys";
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
    queryClient.setQueryData(dashboardQueryKey(bootstrap.dashboard.query), bootstrap.dashboard.data);
  }
  if (bootstrap.bookingPanel) {
    queryClient.setQueryData(bookingPanelQueryKey(bootstrap.bookingPanel.tripInstanceId), bootstrap.bookingPanel.data);
  }
  if (bootstrap.bookingForm) {
    queryClient.setQueryData(
      bookingFormQueryKey(bootstrap.bookingForm.tripInstanceId, bootstrap.bookingForm.bookingId),
      bootstrap.bookingForm.data,
    );
  }
  if (bootstrap.trackerPanel) {
    queryClient.setQueryData(trackerPanelQueryKey(bootstrap.trackerPanel.tripInstanceId), bootstrap.trackerPanel.data);
  }
  if (bootstrap.tripEditor) {
    queryClient.setQueryData(
      tripEditorQueryKey(bootstrap.tripEditor.mode, bootstrap.tripEditor.tripId, bootstrap.tripEditor.query),
      bootstrap.tripEditor.data,
    );
  }
  return queryClient;
}

const queryClient = createQueryClient();

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <ConfirmProvider>
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
        </ConfirmProvider>
      </ToastProvider>
    </QueryClientProvider>
  );
}
