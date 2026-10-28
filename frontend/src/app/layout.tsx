import type { Metadata } from 'next';
import localFont from 'next/font/local';
import './globals.css';
import { Providers } from '@/components/providers';
const inter = localFont({
  src: '../styles/fonts/inter-latin.woff2',
  variable: '--font-inter',
  display: 'swap',
  weight: '100 900',
});
const playfair = localFont({
  src: '../styles/fonts/playfair-display-latin.woff2',
  variable: '--font-playfair',
  display: 'swap',
  weight: '400 900',
});
export const metadata: Metadata = {
  title: 'TANTARA — Legal AI Workspace',
  description: 'AI-powered legal workspace for arbitration law.',
};
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={`${inter.variable} ${playfair.variable}`}>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
