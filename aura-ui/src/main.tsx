import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import './jarvis-clean.css'
import App from './App.tsx'
import HudOverlay from './HudOverlay.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {new URLSearchParams(window.location.search).get('auraHud') === '1'
      ? <HudOverlay /> : <App />}
  </StrictMode>,
)
