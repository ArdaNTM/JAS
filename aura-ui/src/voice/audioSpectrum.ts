/** Visual-only audio measurements. No audio, transcript or network data leaves the client. */
export function createSpectrumPublisher(analyser: AnalyserNode, source: "microphone" | "playback") {
  const bins = new Uint8Array(analyser.frequencyBinCount);
  let last = -Infinity;
  return (now = performance.now()) => {
    if (now - last < 33) return;
    last = now;
    analyser.getByteFrequencyData(bins);
    const bands = Array.from({ length: 64 }, (_, i) => {
      // Log-spaced bands emphasize the speech range without fabricating bins.
      const lo = Math.min(bins.length - 1, Math.floor(Math.pow(bins.length, i / 64) - 1));
      const hi = Math.min(bins.length, Math.max(lo + 1, Math.ceil(Math.pow(bins.length, (i + 1) / 64))));
      let sum = 0;
      for (let j = lo; j < hi; j++) sum += bins[j];
      return sum / (hi - lo) / 255;
    });
    window.dispatchEvent(new CustomEvent("aura:audio-spectrum", { detail: { source, bands } }));
  };
}
