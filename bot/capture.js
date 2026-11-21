// Injected into the Meet page via page.add_init_script (see the MVP spec).
//
// Wraps RTCPeerConnection so every remote audio track is routed into one
// AudioContext -> MediaStreamDestination, then recorded with MediaRecorder
// (audio/webm, 5 s timeslice). Chunks are passed to Python through
// page.expose_function as base64 — not POSTed, because Meet's CSP blocks it.
//
// Stub for M0 — implemented in the Bot milestone (M5).
