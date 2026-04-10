import type { Metadata } from 'next';
import './globals.css';
import TopNav from '@/components/layout/TopNav';

export const metadata: Metadata = {
  title: 'NIFTY Volatility Intelligence',
  description: 'Real-time implied volatility analytics for NIFTY 50 index options',
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full flex flex-col">
        <TopNav />
        <main className="flex-1 overflow-y-auto">
          {children}
        </main>
      </body>
    </html>
  );
}
