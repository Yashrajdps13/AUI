'use client';

import { useState } from 'react';
import ReadonlyRateClient from './ReadonlyRateClient';

export default function ReadonlyPage() {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const [instrumentationDummy, setInstrumentationDummy] = useState(0);

  return (
    <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '2rem' }}>
      <ReadonlyRateClient />
    </div>
  );
}
