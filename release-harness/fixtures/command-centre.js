/* SPDX-License-Identifier: Apache-2.0 */
'use strict';
(() => {
  const el = (id) => document.getElementById(id);

  async function refresh() {
    const buildResponse = await fetch('/api/build-info', { cache: 'no-store' });
    const build = await buildResponse.json();
    const revision = build && build.build ? build.build.revision : '';
    const valid = typeof revision === 'string' && /^[a-f0-9]{40}$/.test(revision);
    el('source-sha').textContent = valid ? revision : 'No valid 40-character source revision';
    el('source-state').textContent = valid
      ? 'Declared by this process · not independently verified'
      : 'Runtime identity incomplete';
    const healthResponse = await fetch('/api/a11oy/v1/atelier/health', { cache: 'no-store' });
    const health = await healthResponse.json();
    const ready = healthResponse.ok && health.ready === true && health.provider === 'xai'
      && health.source_revision === revision;
    el('grok-state').textContent = ready
      ? 'Configured · inference not yet witnessed'
      : 'Unavailable · configuration gates remain';
    el('send').disabled = !ready;
  }

  el('refresh').addEventListener('click', () => {
    refresh().catch(() => {
      el('source-state').textContent = 'Build information unavailable';
      el('send').disabled = true;
    });
  });

  el('turn-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const credential = el('operator-key').value.trim();
    const request = {
      client_request_id: crypto.randomUUID(),
      prompt: el('prompt').value,
      model: el('model').value,
      reasoning_effort: el('effort').value,
      declared: el('classification').value,
    };
    el('turn-status').textContent = 'Checking authorization and policy, then making at most one provider request…';
    try {
      const response = await fetch('/api/a11oy/v1/atelier/turn', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${credential}`,
        },
        body: JSON.stringify(request),
      });
      const value = await response.json();
      const evidence = { ...value };
      delete evidence.answer;
      el('receipt').textContent = JSON.stringify(evidence, null, 2);
      el('receipt-panel').hidden = false;
      if (response.ok && value.state === 'COMPLETED' && typeof value.answer === 'string' && value.answer.trim()) {
        el('answer').textContent = value.answer;
        el('answer').hidden = false;
        el('turn-status').textContent = 'Response matched the submitted request (not any later draft). The server reports a persisted, signature-verified outcome; it is not independently verified in this browser.';
      } else {
        el('answer').hidden = true;
        el('answer').textContent = '';
        el('turn-status').textContent = `No completed answer · ${value.code || value.state || `HTTP ${response.status}`}. No automatic retry was made.`;
      }
    } catch (_error) {
      el('turn-status').textContent = 'Request outcome uncertain. No automatic retry was made.';
    }
  });

  refresh().catch(() => {
    el('source-state').textContent = 'Build information unavailable';
    el('send').disabled = true;
  });
})();
