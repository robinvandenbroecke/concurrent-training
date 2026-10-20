import { useState, useEffect, useRef, useCallback } from 'react';

export function useTimer(initialSeconds: number = 0, direction: 'up' | 'down' = 'down') {
  const [seconds, setSeconds] = useState(initialSeconds);
  const [running, setRunning] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const start = useCallback(() => setRunning(true), []);
  const pause = useCallback(() => setRunning(false), []);
  const reset = useCallback((s = 0) => { setRunning(false); setSeconds(s); }, []);

  useEffect(() => {
    if (running) {
      const started = Date.now();
      const initial = seconds;
      intervalRef.current = setInterval(() => {
        const delta = Math.floor((Date.now() - started) / 1000);
        setSeconds(direction === 'up' ? initial + delta : Math.max(0, initial - delta));
      }, 1000);
    } else {
      if (intervalRef.current) clearInterval(intervalRef.current);
    }
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [running, direction]);

  const formatted = `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;

  return { seconds, running, formatted, start, pause, reset };
}
