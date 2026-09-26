// Point this at your backend if it's not running on the default local port.
// Local development keeps using the Docker Compose backend; deployed builds
// use the public Cloud Run API unless an explicit override is provided.
const isLocal = ["localhost", "127.0.0.1"].includes(window.location.hostname);
const defaultApiBase = isLocal
  ? "http://127.0.0.1:8000"
  : "https://lexguide-ai-backend-3t4kdfldba-el.a.run.app";
window.LEXGUIDE_API_BASE = window.LEXGUIDE_API_BASE || defaultApiBase;
