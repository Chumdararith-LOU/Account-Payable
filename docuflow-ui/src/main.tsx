import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App' // This will now pull your new App.tsx
import './index.css'    // This pulls your new Tailwind CSS

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
