import { QueryClient } from '@tanstack/react-query';

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30 * 1000,        // 30s before data considered stale
      gcTime: 5 * 60 * 1000,       // 5min cache retention (garbage collection)
      retry: 2,                     // Retry failed requests twice
      refetchOnWindowFocus: false,  // Don't refetch when window regains focus
    },
  },
});
