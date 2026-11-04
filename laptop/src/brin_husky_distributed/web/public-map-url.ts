// Used only by the isolated public dashboard build, including Socket.IO maps.
export function publicMapImageUrl(value: string, apiBase: string): string {
  try {
    const url = new URL(value, apiBase);
    if (url.pathname.startsWith('/cache/')) {
      return `${apiBase}${url.pathname}${url.search}`;
    }
  } catch {
    // Keep non-URL map payloads unchanged.
  }
  return value;
}
