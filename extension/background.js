// Service worker: performs the actual network call to the local ReadRepo
// server and relays the NDJSON stream back to the content script. This
// indirection is required because the content script runs in the HTTPS
// github.com page, where calling http://localhost is blocked as mixed
// content; the background worker is exempt (via host_permissions).

const SERVER = "http://localhost:8000";

chrome.runtime.onConnect.addListener((port) => {
  if (port.name !== "chat") return;

  port.onMessage.addListener(async (request) => {
    try {
      const res = await fetch(`${SERVER}/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request),
      });

      if (!res.ok) {
        port.postMessage({ type: "error", detail: `Server returned ${res.status}` });
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        let newline;
        while ((newline = buffer.indexOf("\n")) >= 0) {
          const line = buffer.slice(0, newline).trim();
          buffer = buffer.slice(newline + 1);
          if (line) {
            try {
              port.postMessage(JSON.parse(line));
            } catch {
              // ignore malformed partial line
            }
          }
        }
      }
    } catch (err) {
      port.postMessage({
        type: "error",
        detail: `Could not reach the ReadRepo server at ${SERVER}. Is it running?`,
      });
    }
  });
});
