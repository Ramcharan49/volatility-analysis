import type { Metadata } from 'next';
import './globals.css';
import BottomTabBar from '@/components/layout/BottomTabBar';

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
        <main className="flex-1 overflow-y-auto pb-16">
          {children}
        </main>
        <BottomTabBar />
      </body>
    </html>
  );
}
