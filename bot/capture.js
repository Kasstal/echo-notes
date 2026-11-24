// Injected into the Meet page with page.add_init_script, before any page script runs.
//
// Wraps RTCPeerConnection so every remote audio track is mixed into one AudioContext ->
// MediaStreamDestination, which MediaRecorder records as audio/webm in 5 s slices. Slices
// go to Python through the exposed function `echonotesChunk` as base64: Meet's CSP blocks a
// POST from the page to the backend.
(() => {
  if (window.top !== window || window.__echonotes) return;

  const TIMESLICE_MS = 5000;
  let ctx = null;
  let dest = null;
  let recorder = null;
  let pending = Promise.resolve();
  const tracks = new Map();

  function toBase64(buffer) {
    const bytes = new Uint8Array(buffer);
    let binary = "";
    for (let i = 0; i < bytes.length; i += 0x8000) {
      binary += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
    }
    return btoa(binary);
  }

  function startRecorder() {
    ctx = new AudioContext();
    dest = ctx.createMediaStreamDestination();
    recorder = new MediaRecorder(dest.stream, { mimeType: "audio/webm" });
    recorder.ondataavailable = (event) => {
      if (!event.data || event.data.size === 0) return;
      // Chained so slices reach Python in order even though each send is async.
      pending = pending
        .then(() => event.data.arrayBuffer())
        .then((buf) => window.echonotesChunk(toBase64(buf)))
        .catch((err) => console.error("echonotes: chunk lost", err));
    };
    recorder.start(TIMESLICE_MS);
  }

  function addTrack(track) {
    if (track.kind !== "audio" || tracks.has(track.id)) return;
    if (!recorder) startRecorder();
    const stream = new MediaStream([track]);
    // Chrome feeds a remote WebRTC track into WebAudio only while some media element is
    // playing it; without this the recording is silent (checked on a local loopback call).
    const sink = new Audio();
    sink.muted = true;
    sink.srcObject = stream;
    sink.play().catch(() => {});
    const source = ctx.createMediaStreamSource(stream);
    source.connect(dest);
    // Only for the bot's log: how loud each track is, to tell "no one spoke" from "no sound".
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 2048;
    source.connect(analyser);
    tracks.set(track.id, { track, analyser, peak: 0 });
    track.addEventListener("ended", () => {
      source.disconnect();
      sink.srcObject = null;
      tracks.delete(track.id);
    });
    if (ctx.state === "suspended") ctx.resume();
  }

  function level(entry) {
    const buf = new Float32Array(entry.analyser.fftSize);
    entry.analyser.getFloatTimeDomainData(buf);
    let sum = 0;
    for (const v of buf) sum += v * v;
    return Math.sqrt(sum / buf.length);
  }

  // Peak level per track since the last status() call, sampled twice a second.
  setInterval(() => {
    for (const entry of tracks.values()) entry.peak = Math.max(entry.peak, level(entry));
  }, 500);

  const Original = window.RTCPeerConnection;
  class RecordingPeerConnection extends Original {
    constructor(...args) {
      super(...args);
      this.addEventListener("track", (event) => addTrack(event.track));
    }
  }
  window.RTCPeerConnection = RecordingPeerConnection;

  window.__echonotes = {
    status: () => {
      const peaks = [...tracks.values()].map((entry) => {
        const peak = entry.peak;
        entry.peak = 0;
        return {
          muted: entry.track.muted,
          dbfs: peak > 0 ? Math.round(20 * Math.log10(peak)) : null,
        };
      });
      return {
        recording: recorder !== null && recorder.state === "recording",
        context: ctx ? ctx.state : null,
        tracks: peaks,
      };
    },
    // Resolves once the last slice has been handed to Python.
    stop: () =>
      new Promise((resolve) => {
        if (!recorder || recorder.state === "inactive") return pending.then(resolve);
        recorder.addEventListener("stop", () => setTimeout(() => pending.then(resolve), 0));
        recorder.stop();
      }),
  };
})();
