/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        navy: { DEFAULT: '#1B3B5A', light: '#2C5E8A', dark: '#12263b' },
        bg: '#F0F4F8',
        panel: '#ffffff',
        border: '#ccc',
        tb: '#dfe5eb',
        z: '#f4f6f8',
        success: '#4CAF50',
        warning: '#F57C00',
        danger: '#E53935',
      },
      fontFamily: {
        sans: ['Tahoma', 'Verdana', 'Arial', 'sans-serif'],
      },
      fontSize: {
        base: ['12px', '1.5'], // Force 12px base for the dense enterprise look
      },
      backgroundImage: {
        'win7': 'linear-gradient(to bottom, #2C5E8A, #1B3B5A)',
        'win7-panel': 'linear-gradient(to bottom, #f4f6f8, #dfe5eb)',
        'win7-btn': 'linear-gradient(to bottom, #6ea4d4 0%, #2C5E8A 50%, #1B3B5A 51%, #25527f 100%)',
      },
      boxShadow: {
        'retro-btn': 'inset 0 1px 0 rgba(255,255,255,0.3), 0 1px 3px rgba(0,0,0,0.2)',
        'inset-input': 'inset 1px 1px 3px rgba(0,0,0,0.25)',
      }
    },
  },
  plugins: [],
}
