import type { Metadata } from 'next';
import { Providers } from './providers';

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
        {/*
          Providers is a Client Component that establishes the agent WebSocket
          connection. All pages rendered inside will be visible to the agent
          if they are Client Components with useState calls.
        */}
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
