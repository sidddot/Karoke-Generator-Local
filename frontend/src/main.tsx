import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import App from './App'
import Library from './pages/Library'
import Player from './pages/Player'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<App />}>
          <Route index element={<Library />} />
          <Route path="play/:id" element={<Player />} />
        </Route>
      </Routes>
    </BrowserRouter>
  </React.StrictMode>
)
