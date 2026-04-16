import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route } from "react-router-dom";

import { DashboardPage } from "./routes/DashboardPage";
import { frontendBootstrap } from "./lib/bootstrap";

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
      [
        "booking-panel",
        bootstrap.bookingPanel.tripInstanceId,
        bootstrap.bookingPanel.mode,
        bootstrap.bookingPanel.bookingId,
      ],
      bootstrap.bookingPanel.data,
    );
  }
  if (bootstrap.trackerPanel) {
    queryClient.setQueryData(
      ["tracker-panel", bootstrap.trackerPanel.tripInstanceId],
      bootstrap.trackerPanel.data,
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
          <Route path="*" element={<DashboardPage />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
