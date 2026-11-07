import { useEffect, useState } from 'react';
import { initializeTelegram } from '../telegram';

export type Theme = 'light' | 'dark';

export function useTelegramTheme() {
  const [theme, setTheme] = useState<Theme>(
    () => initializeTelegram()?.colorScheme ?? 'light',
  );

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
  }, [theme]);

  useEffect(() => {
    const webApp = initializeTelegram();
    if (!webApp) return;
    const updateTheme = () => setTheme(webApp.colorScheme);
    webApp.onEvent('themeChanged', updateTheme);
    return () => webApp.offEvent('themeChanged', updateTheme);
  }, []);

  return {
    theme,
    toggleTheme: () =>
      setTheme((value) => (value === 'dark' ? 'light' : 'dark')),
  };
}
