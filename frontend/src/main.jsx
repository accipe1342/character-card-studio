import { StrictMode } from 'react'

// Restore theme before first render to avoid flash
const savedTheme = localStorage.getItem('nier-theme') || 'light'
document.documentElement.setAttribute('data-theme', savedTheme)
import { createRoot } from 'react-dom/client'
import './index.css'
import './nier-animations.css'
import App from './App.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
