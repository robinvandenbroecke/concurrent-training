import test from 'node:test';
import assert from 'node:assert/strict';
import React, { act } from 'react';
import { JSDOM } from 'jsdom';

test('onboarding → plan → workout → navigation → reload → save → real local history', async () => {
  const dom = new JSDOM('<div id="root"></div>', { url: 'https://example.test/concurrent-training/', pretendToBeVisual: true });
  const w = dom.window;
  Object.assign(globalThis, { window: w, document: w.document, localStorage: w.localStorage, HTMLElement: w.HTMLElement,
    IS_REACT_ACT_ENVIRONMENT: true });
  Object.defineProperty(globalThis, 'navigator', { value: w.navigator, configurable: true });
  w.confirm = () => true;
  const { createRoot } = await import('react-dom/client');
  const { default: App } = await import('../src/App.tsx');
  const { readSessions, readDraft } = await import('../src/api/local.ts');
  const host = document.getElementById('root')!;
  let root = createRoot(host);
  const flush = async () => { await act(async () => { await new Promise(r => setTimeout(r, 0)); }); };
  const click = async (el: Element | null | undefined) => { assert.ok(el, 'control exists'); await act(async () => { el.dispatchEvent(new w.MouseEvent('click', { bubbles: true })); }); await flush(); };
  const visible = (el: Element) => { for (let p: Element | null = el; p; p = p.parentElement) if ((p as HTMLElement).style?.display === 'none') return false; return true; };
  const button = (text: RegExp, scope: Element = host) => [...scope.querySelectorAll('button')].find(b => visible(b) && text.test(b.textContent?.trim() ?? ''));
  const fill = async (el: HTMLInputElement, value: string) => {
    assert.ok(el, 'input exists');
    await act(async () => {
      Object.getOwnPropertyDescriptor(w.HTMLInputElement.prototype, 'value')!.set!.call(el, value);
      el.dispatchEvent(new w.Event('input', { bubbles: true }));
      el.dispatchEvent(new w.Event('change', { bubbles: true }));
    });
  };
  const activeTraining = () => [...host.querySelectorAll('main > div')].find(x => (x as HTMLElement).style.display === 'block')!;
  try {
    await act(async () => { root.render(<App />); }); await flush();
    await fill(host.querySelector('input[placeholder="Naam"]')!, 'Testatleet');
    await click(button(/^Volgende$/));
    await click(button(/^Kracht/)); await click(button(/^Volgende$/));
    const labels = ['Zo', 'Ma', 'Di', 'Wo', 'Do', 'Vr', 'Za'];
    const today = new Date().getDay();
    for (let d = 0; d < 7; d++) {
      const b = button(new RegExp(`^${labels[d]}$`))!;
      const desired = d === today || d === (today + 1) % 7;
      if (b.classList.contains('selected') !== desired) await click(b);
    }
    await click(button(/^Volgende$/));
    const weights = [...host.querySelectorAll('input[type="number"]')] as HTMLInputElement[];
    await fill(weights[0], '50'); await fill(weights[1], '40');
    await click(button(/^Volgende$/)); await click(button(/^Start$/));
    assert.match(host.textContent!, /Onbekend/); assert.doesNotMatch(host.textContent!, /82%/);
    await click(button(/^Start training$/)); await click(button(/Start training/));
    let screen = activeTraining();
    const row = button(/Bevestig set 1/, screen)!.parentElement!;
    const inputs = row.querySelectorAll('input');
    await fill(inputs[0], '42.5'); await fill(inputs[1], '3');
    await click(button(/RPE \/ snelheid/, row));
    await fill(row.querySelector('input[min="1"]')!, '8');
    await click(button(/Bevestig set 1/, screen));
    await click(button(/^Overslaan$/));
    await click(button(/^Week$/)); await click(button(/^Training$/));
    assert.match(activeTraining().textContent!, /42.5 kg/);
    assert.equal(Object.values(readDraft()!.completed)[0][0].completedReps, 3);
    await act(async () => root.unmount());
    root = createRoot(host); await act(async () => root.render(<App />)); await flush();
    await click(button(/^Training$/));
    screen = activeTraining(); assert.match(screen.textContent!, /42.5 kg/);
    await click(button(/Training afronden/, screen));
    assert.match(activeTraining().textContent!, /Training afgerond/);
    assert.equal(readDraft(), null);
    const sessions = readSessions(); assert.equal(sessions.length, 1);
    assert.deepEqual(sessions[0].exercises![0].sets[0].velocities, [null, null, null]);
    assert.equal(sessions[0].exercises![0].sets[0].rpe, 8);
    await click(button(/^Historie$/));
    assert.match(activeTraining().textContent!, /42.5 kg × 3 reps/);
    assert.match(activeTraining().textContent!, /Alleen lokaal opgeslagen/);
  } finally {
    await act(async () => root.unmount()); dom.window.close();
  }
});
