/**
 * Direct ERG control of a smart trainer over the Bluetooth SIG Fitness Machine
 * Service (FTMS 1.0, service 0x1826). Only the standard protocol is used; no
 * vendor protocol is implemented.
 *
 * Safety design:
 *  - control is requested explicitly and only after the user picked the device;
 *  - a target is sent only if the trainer advertises "power target setting";
 *  - every target is clamped to the trainer's own supported range AND to the
 *    user's maximum; nothing above that limit can be written;
 *  - pause and stop first lower the target to the floor, then send the FTMS
 *    stop/pause procedure, so a trainer that ignores "pause" is still light;
 *  - a lost link, lost control permission, a refused command or silence from
 *    the trainer moves to a non-controlling state. Nothing is resumed
 *    automatically: after reconnecting the user must resume, and the first
 *    target is the floor.
 * What a disconnected trainer does on its own is firmware behaviour that this
 * app cannot command; see INTEGRATION_STATUS.md.
 */
export const FTMS_SERVICE = 0x1826, CYCLING_POWER_SERVICE = 0x1818;
export const CH = { feature: 0x2acc, indoorBikeData: 0x2ad2, powerRange: 0x2ad8, controlPoint: 0x2ad9, status: 0x2ada, cyclingPowerMeasurement: 0x2a63 };
export const OP = { requestControl: 0x00, reset: 0x01, setTargetPower: 0x05, startOrResume: 0x07, stopOrPause: 0x08, response: 0x80 };
export const RESULT: Record<number, string> = { 1: 'success', 2: 'op_code_not_supported', 3: 'invalid_parameter', 4: 'operation_failed', 5: 'control_not_permitted' };

export interface BikeData { speedKph?: number; cadenceRpm?: number; powerW?: number; heartRateBpm?: number; elapsedSeconds?: number }

/** Indoor Bike Data (0x2AD2). Field presence follows the flags; absent fields stay undefined. */
export function parseIndoorBikeData(view: DataView): BikeData {
  if (view.byteLength < 2) throw new Error('Indoor Bike Data te kort');
  const flags = view.getUint16(0, true), out: BikeData = {};
  let o = 2;
  const need = (n: number) => { if (o + n > view.byteLength) throw new Error('Indoor Bike Data afgebroken'); };
  if (!(flags & 0x0001)) { need(2); out.speedKph = view.getUint16(o, true) / 100; o += 2; }       // bit 0 = "more data": speed absent
  if (flags & 0x0002) { need(2); o += 2; }                                                          // average speed
  if (flags & 0x0004) { need(2); out.cadenceRpm = view.getUint16(o, true) / 2; o += 2; }
  if (flags & 0x0008) { need(2); o += 2; }                                                          // average cadence
  if (flags & 0x0010) { need(3); o += 3; }                                                          // total distance (uint24)
  if (flags & 0x0020) { need(2); o += 2; }                                                          // resistance level
  if (flags & 0x0040) { need(2); out.powerW = view.getInt16(o, true); o += 2; }
  if (flags & 0x0080) { need(2); o += 2; }                                                          // average power
  if (flags & 0x0100) { need(5); o += 5; }                                                          // expended energy
  if (flags & 0x0200) { need(1); out.heartRateBpm = view.getUint8(o); o += 1; }
  if (flags & 0x0400) { need(1); o += 1; }                                                          // metabolic equivalent
  if (flags & 0x0800) { need(2); out.elapsedSeconds = view.getUint16(o, true); o += 2; }
  return out;
}

/** Cycling Power Measurement (0x2A63): measurement only, never control. */
export function parseCyclingPower(view: DataView): { powerW: number; crankRevolutions?: number; crankEventTime1024?: number } {
  if (view.byteLength < 4) throw new Error('Cycling Power Measurement te kort');
  const flags = view.getUint16(0, true), out: { powerW: number; crankRevolutions?: number; crankEventTime1024?: number } = { powerW: view.getInt16(2, true) };
  let o = 4;
  if (flags & 0x01) o += 1;
  if (flags & 0x04) o += 2;
  if (flags & 0x10) o += 6;
  if ((flags & 0x20) && o + 4 <= view.byteLength) { out.crankRevolutions = view.getUint16(o, true); out.crankEventTime1024 = view.getUint16(o + 2, true); }
  return out;
}
/** Cadence from two successive crank readings (16-bit counters wrap). Undefined when no new crank event. */
export function cadenceFromCrank(prev: { crankRevolutions?: number; crankEventTime1024?: number }, next: { crankRevolutions?: number; crankEventTime1024?: number }): number | undefined {
  if (prev.crankRevolutions === undefined || next.crankRevolutions === undefined || prev.crankEventTime1024 === undefined || next.crankEventTime1024 === undefined) return undefined;
  const revs = (next.crankRevolutions - prev.crankRevolutions + 0x10000) % 0x10000, ticks = (next.crankEventTime1024 - prev.crankEventTime1024 + 0x10000) % 0x10000;
  return ticks === 0 ? undefined : revs / (ticks / 1024) * 60;
}

export function parseFeature(view: DataView): { powerTarget: boolean; cadence: boolean; powerMeasurement: boolean } {
  if (view.byteLength < 8) throw new Error('Fitness Machine Feature te kort');
  const machine = view.getUint32(0, true), target = view.getUint32(4, true);
  return { cadence: !!(machine & (1 << 1)), powerMeasurement: !!(machine & (1 << 14)), powerTarget: !!(target & (1 << 3)) };
}
export interface PowerRange { minW: number; maxW: number; stepW: number }
export function parsePowerRange(view: DataView): PowerRange {
  if (view.byteLength < 6) throw new Error('Supported Power Range te kort');
  const range = { minW: view.getInt16(0, true), maxW: view.getInt16(2, true), stepW: view.getUint16(4, true) || 1 };
  if (range.maxW <= 0 || range.maxW < range.minW) throw new Error('Trainer meldt een ongeldig vermogensbereik');
  return range;
}
export function encodeTargetPower(watts: number): Uint8Array {
  if (!Number.isInteger(watts) || watts < -32768 || watts > 32767) throw new Error('Doelvermogen buiten het protocolbereik');
  const bytes = new Uint8Array(3);
  new DataView(bytes.buffer).setUint8(0, OP.setTargetPower);
  new DataView(bytes.buffer).setInt16(1, watts, true);
  return bytes;
}
export function parseControlResponse(view: DataView): { requestOp: number; result: string } | null {
  if (view.byteLength < 3 || view.getUint8(0) !== OP.response) return null;
  return { requestOp: view.getUint8(1), result: RESULT[view.getUint8(2)] ?? 'unknown' };
}

// Minimal structural types so the controller runs against Web Bluetooth and against a simulator in tests.
export interface CharacteristicLike {
  readValue(): Promise<DataView>;
  writeValueWithResponse(value: BufferSource): Promise<void>;
  startNotifications(): Promise<unknown>;
  addEventListener(type: 'characteristicvaluechanged', listener: (event: { target: unknown }) => void): void;
}
export interface ServiceLike { getCharacteristic(uuid: number): Promise<CharacteristicLike> }
export interface ServerLike { connected: boolean; getPrimaryService(uuid: number): Promise<ServiceLike>; disconnect(): void }
export interface DeviceLike { name?: string; gatt?: { connect(): Promise<ServerLike> }; addEventListener(type: 'gattserverdisconnected', listener: () => void): void }

export type TrainerState = 'idle' | 'connecting' | 'measuring' | 'controlling' | 'paused' | 'disconnected' | 'control_lost' | 'error';
export interface TrainerEvents { onState?: (state: TrainerState, detail?: string) => void; onData?: (data: BikeData, at: number) => void }
export interface TrainerLimits { maxPowerW: number; floorPowerW: number }

const value = (event: { target: unknown }) => (event.target as { value: DataView }).value;

export class FtmsTrainer {
  state: TrainerState = 'idle';
  range: PowerRange | null = null;
  canControl = false;
  lastTargetW: number | null = null;
  lastDataAt = 0;
  private control: CharacteristicLike | null = null;
  private server: ServerLike | null = null;
  private queue: Promise<unknown> = Promise.resolve();
  private pending: { op: number; resolve: (result: string) => void } | null = null;

  constructor(private device: DeviceLike, private limits: TrainerLimits, private events: TrainerEvents = {},
    private now: () => number = () => Date.now(), private responseTimeoutMs = 3000) {
    if (!(limits.maxPowerW > 0) || limits.floorPowerW < 0 || limits.floorPowerW > limits.maxPowerW) throw new Error('Ongeldige vermogensgrenzen');
  }
  private set(state: TrainerState, detail?: string) { this.state = state; this.events.onState?.(state, detail); }

  /** Connect, read capabilities and (only if supported) request control. Never sends a target. */
  async connect(): Promise<void> {
    if (!this.device.gatt) throw new Error('Dit apparaat ondersteunt geen Bluetooth Low Energy GATT.');
    this.set('connecting');
    this.device.addEventListener('gattserverdisconnected', () => { this.control = null; this.pending?.resolve('disconnected'); this.set('disconnected'); });
    try {
      this.server = await this.device.gatt.connect();
      const service = await this.server.getPrimaryService(FTMS_SERVICE);
      const feature = parseFeature(await (await service.getCharacteristic(CH.feature)).readValue());
      const data = await service.getCharacteristic(CH.indoorBikeData);
      data.addEventListener('characteristicvaluechanged', e => { try { this.lastDataAt = this.now(); this.events.onData?.(parseIndoorBikeData(value(e)), this.lastDataAt); } catch { /* ignore one malformed packet */ } });
      await data.startNotifications();
      this.canControl = false;
      if (feature.powerTarget) {
        this.range = parsePowerRange(await (await service.getCharacteristic(CH.powerRange)).readValue());
        const control = await service.getCharacteristic(CH.controlPoint);
        control.addEventListener('characteristicvaluechanged', e => {
          const response = parseControlResponse(value(e));
          if (response && this.pending && response.requestOp === this.pending.op) this.pending.resolve(response.result);
        });
        await control.startNotifications();
        const status = await service.getCharacteristic(CH.status);
        status.addEventListener('characteristicvaluechanged', e => { if (value(e).byteLength && value(e).getUint8(0) === 0xff) { this.control = null; this.set('control_lost'); } });
        await status.startNotifications();
        this.control = control;
        await this.command(new Uint8Array([OP.requestControl]));
        this.canControl = true;
      }
      this.set(this.canControl ? 'paused' : 'measuring', this.canControl ? undefined : 'trainer_has_no_erg_target');
    } catch (error) {
      this.control = null; this.canControl = false;
      if (this.state !== 'disconnected') this.set('error', (error as Error).message);
      throw error;
    }
  }

  private command(bytes: Uint8Array): Promise<void> {
    const run = async () => {
      const control = this.control;
      if (!control) throw new Error('Geen controle over de trainer.');
      const result = await new Promise<string>((resolve, reject) => {
        const timer = setTimeout(() => resolve('timeout'), this.responseTimeoutMs);
        this.pending = { op: bytes[0], resolve: r => { clearTimeout(timer); resolve(r); } };
        control.writeValueWithResponse(bytes).catch(error => { clearTimeout(timer); reject(error); });
      }).finally(() => { this.pending = null; });
      if (result !== 'success') throw new Error(`Trainer weigerde de opdracht (${result}).`);
    };
    // GATT operations must not overlap; a failed command does not block later ones.
    const next = this.queue.catch(() => {}).then(run);
    this.queue = next;
    return next;
  }

  /** Clamp to the trainer's range and the user's limit, then round to the trainer's step. */
  clamp(watts: number): number {
    if (!this.range) throw new Error('Vermogensbereik van de trainer is onbekend.');
    const high = Math.min(this.range.maxW, this.limits.maxPowerW), low = Math.max(this.range.minW, 0);
    const bounded = Math.min(high, Math.max(low, Number.isFinite(watts) ? watts : low));
    return Math.max(low, Math.min(high, Math.round(bounded / this.range.stepW) * this.range.stepW));
  }
  get floorW(): number { return this.clamp(this.limits.floorPowerW); }

  private async fail(error: unknown): Promise<never> {
    if (this.state !== 'disconnected' && this.state !== 'control_lost') { this.lastTargetW = null; this.set('error', (error as Error).message); }
    throw error;
  }

  /** Begin or resume ERG control. The first target is always the floor; the caller raises it afterwards. */
  async start(): Promise<void> {
    if (!this.canControl || !this.control) throw new Error('Deze trainer kan niet worden aangestuurd.');
    try {
      await this.command(encodeTargetPower(this.floorW)); this.lastTargetW = this.floorW;
      await this.command(new Uint8Array([OP.startOrResume]));
      this.set('controlling');
    } catch (error) { await this.fail(error); }
  }

  async setTargetPower(watts: number): Promise<number> {
    if (this.state !== 'controlling') throw new Error('De trainer wordt nu niet aangestuurd.');
    const target = this.clamp(watts);
    if (target === this.lastTargetW) return target;
    try { await this.command(encodeTargetPower(target)); this.lastTargetW = target; } catch (error) { await this.fail(error); }
    return target;
  }

  /** Lower to the floor first, then pause. Safe to call in any state. */
  async pause(): Promise<void> { await this.halt(2, 'paused'); }
  async stop(): Promise<void> {
    await this.halt(1, 'idle');
    try { this.server?.disconnect(); } catch { /* already gone */ }
  }
  private async halt(parameter: 1 | 2, state: TrainerState): Promise<void> {
    if (!this.control) return;
    const wasControlling = this.state === 'controlling';
    let problem: unknown = null;
    if (wasControlling) {
      try { await this.command(encodeTargetPower(this.floorW)); this.lastTargetW = this.floorW; } catch (error) { problem = error; }
      try { await this.command(new Uint8Array([OP.stopOrPause, parameter])); } catch (error) { problem ??= error; }
    }
    if (this.state === 'disconnected' || this.state === 'control_lost') return;
    if (problem) this.set('error', (problem as Error).message); else this.set(state);
  }

  /** True when the trainer has been silent for too long while it should be sending data. */
  silent(maxGapMs = 5000): boolean { return this.lastDataAt > 0 && this.now() - this.lastDataAt > maxGapMs; }
}

export interface BluetoothSupport { available: boolean; reason?: 'no_api' | 'insecure_context' }
/** Web Bluetooth exists in Chromium browsers (incl. Chrome on Android) on HTTPS; not in Safari, Firefox or Android WebView. */
export function bluetoothSupport(nav: { bluetooth?: unknown } = navigator as unknown as { bluetooth?: unknown }, secure = globalThis.isSecureContext): BluetoothSupport {
  if (!secure) return { available: false, reason: 'insecure_context' };
  if (!nav.bluetooth) return { available: false, reason: 'no_api' };
  return { available: true };
}
export async function requestTrainer(): Promise<DeviceLike> {
  const bluetooth = (navigator as unknown as { bluetooth: { requestDevice(options: unknown): Promise<DeviceLike> } }).bluetooth;
  // The browser shows its own chooser; only devices advertising FTMS are listed.
  return bluetooth.requestDevice({ filters: [{ services: [FTMS_SERVICE] }], optionalServices: [CYCLING_POWER_SERVICE] });
}
