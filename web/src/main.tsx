import { notifyManager, QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from './App'
import { TooltipProvider } from './components/ui'
import { ApiError, setUnauthorizedHandler } from './lib/api'
import './index.css'

// Deliver cache updates synchronously. Editors write every keystroke into the
// query cache; with the default (deferred) delivery, React would reset controlled
// inputs between keystrokes and drop characters when typing quickly.
notifyManager.setScheduler((callback) => callback())

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: (count, error) =>
        !(error instanceof ApiError && error.status >= 400 && error.status < 500) && count < 2,
    },
  },
})

setUnauthorizedHandler(() => queryClient.setQueryData(['me'], { authenticated: false }))

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <App />
      </TooltipProvider>
    </QueryClientProvider>
  </StrictMode>,
)
