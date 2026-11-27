import 'leaflet/dist/leaflet.css'; // Leaflet's own styles: without this the map tiles scatter
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './index.css';
import './app.css';
import App from './App.tsx';

const root = document.getElementById('root');
if (!root) throw new Error('#root element missing from index.html');

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
