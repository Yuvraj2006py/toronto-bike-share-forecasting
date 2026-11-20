import { StrictMode } from 'react'
import { flushSync } from 'react-dom'
import { createRoot } from 'react-dom/client'
import App from './App'
import './styles.css'

const root = createRoot(document.getElementById('root') as HTMLElement)
// Commit the first frame synchronously so the hero exists before motion.js runs its entrance.
flushSync(() => {
  root.render(
    <StrictMode>
      <App />
    </StrictMode>,
  )
})
