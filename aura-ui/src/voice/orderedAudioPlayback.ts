/** Cancellable, ordered Web Audio playback for generated local speech chunks. */
export class OrderedAudioPlayback {
  private context: AudioContext | null = null;
  private tail: Promise<void> = Promise.resolve();
  private generation = 0;
  private current: AudioBufferSourceNode | null = null;

  private async audioContext(): Promise<AudioContext> {
    if (!this.context || this.context.state === "closed") this.context = new AudioContext();
    if (this.context.state === "suspended") await this.context.resume();
    return this.context;
  }

  enqueue(blob: Blob, onStart?: () => void): Promise<void> {
    const generation = this.generation;
    const job = async () => {
      const context = await this.audioContext();
      const data = await blob.arrayBuffer();
      const decoded = await context.decodeAudioData(data.slice(0));
      if (generation !== this.generation) return;
      await new Promise<void>((resolve, reject) => {
        const source = context.createBufferSource();
        this.current = source;
        source.buffer = decoded;
        source.connect(context.destination);
        source.onended = () => { if (this.current === source) this.current = null; resolve(); };
        try { onStart?.(); source.start(); } catch (error) { reject(error); }
      });
    };
    this.tail = this.tail.then(job, job);
    return this.tail;
  }

  cancel(): void {
    this.generation += 1;
    if (this.current) {
      try { this.current.stop(); } catch { /* already stopped */ }
      this.current = null;
    }
    this.tail = Promise.resolve();
  }

  async close(): Promise<void> {
    this.cancel();
    if (this.context && this.context.state !== "closed") await this.context.close();
    this.context = null;
  }
}
