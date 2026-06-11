import './globals.css';
import type { Metadata } from 'next';
import { Providers } from './providers';
import StateWatchTerminal from './components/StateWatchTerminal';

export const metadata: Metadata = {
  title: 'nextjs-flow | react-agent-bridge',
  description: 'Next.js App Router example for react-agent-bridge',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <Providers>
          <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
            {children}
          </div>
          <StateWatchTerminal />
        </Providers>
      </body>
    </html>
  );
}
