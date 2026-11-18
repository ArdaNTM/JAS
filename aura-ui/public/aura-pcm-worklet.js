/* Zero-output, 100ms mono PCM capture at AudioContext 16 kHz.
 * Capture requires the user's explicit microphone permission.
 * Audio is sent only through the local authenticated speech endpoint.
 */
class AuraPCMProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.samples = new Float32Array(1600);
    this.position = 0;
  }
  process(inputs) {
    const channel = inputs[0]?.[0];
    if (channel) {
      for (let i = 0; i < channel.length; i++) {
        this.samples[this.position++] = Math.max(-1, Math.min(1, channel[i]));
        if (this.position === 1600) {
          const buffer = this.samples.buffer;
          this.port.postMessage(buffer, [buffer]);
          this.samples = new Float32Array(1600);
          this.position = 0;
        }
      }
    }
    return true;
  }
}
registerProcessor("aura-pcm-processor", AuraPCMProcessor);
