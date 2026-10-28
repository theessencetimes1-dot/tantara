import type { Config } from 'tailwindcss';
const config: Config = { content: ['./src/**/*.{ts,tsx}'], theme: { extend: { colors: { navy: '#0A1730', indigo: '#4F46E5', ink: '#0F172A', muted: '#64748B', line: '#E7EAF0' }, fontFamily: { sans: ['var(--font-inter)', 'Arial', 'sans-serif'], serif: ['var(--font-playfair)', 'Georgia', 'serif'] }, boxShadow: { card: '0 1px 2px rgba(16,24,40,.04)', elevated: '0 12px 28px -14px rgba(16,24,40,.16)' } } }, plugins: [] };
export default config;
