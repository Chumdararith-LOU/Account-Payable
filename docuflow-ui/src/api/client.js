import axios from 'axios';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://100.88.94.91:8001',
  headers: {
    'X-API-Key': import.meta.env.VITE_API_KEY || '',
  },
});

export default api;
