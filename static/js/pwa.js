/* Perfect Palate - registers the service worker, offers install, and tells people what is saved / offline. */
(function () {
  'use strict';
  const T = (k, v) => (window.PPI18N ? PPI18N.t(k, v) : k);
  let toastEl;
  function note(text, actionLabel, action, sticky) {
    if (toastEl) toastEl.remove();
    toastEl = document.createElement('div');
    toastEl.className = 'pp-pwa-note'; toastEl.setAttribute('role', 'status');
    toastEl.textContent = text;
    if (actionLabel) { const b = document.createElement('button'); b.type = 'button'; b.textContent = actionLabel; b.onclick = action; toastEl.appendChild(b); }
    document.body.appendChild(toastEl);
    if (!sticky) { const el = toastEl; setTimeout(() => { if (el.isConnected) el.remove(); }, 5000); }
  }
  const css = document.createElement('style');
  css.textContent = '.pp-pwa-note{position:fixed;left:50%;bottom:18px;transform:translateX(-50%);z-index:9999;max-width:calc(100vw - 32px);display:flex;gap:.8rem;align-items:center;background:#16303f;color:#faf8f4;border:1px solid rgba(226,186,46,.55);border-radius:14px;padding:.7rem 1rem;font:600 .82rem/1.35 system-ui,sans-serif;box-shadow:0 8px 28px rgba(0,0,0,.35)}.pp-pwa-note button{min-height:36px;border-radius:999px;border:0;background:#e2ba2e;color:#1a2a33;font:700 .78rem system-ui,sans-serif;padding:.4rem .9rem;cursor:pointer}';
  document.head.appendChild(css);

  // ---- offline / online ----
  function connection() { if (!navigator.onLine) note(T('offline.offline'), null, null, true); else if (toastEl && toastEl.dataset.off) toastEl.remove(); }
  window.addEventListener('offline', () => { connection(); if (toastEl) toastEl.dataset.off = '1'; });
  window.addEventListener('online', () => { if (toastEl && toastEl.dataset.off) toastEl.remove(); });
  if (!navigator.onLine) window.addEventListener('DOMContentLoaded', () => { connection(); if (toastEl) toastEl.dataset.off = '1'; });

  // ---- install ----
  let deferred = null;
  window.addEventListener('beforeinstallprompt', e => {
    e.preventDefault(); deferred = e;
    document.querySelectorAll('[data-pp-install]').forEach(b => { b.hidden = false; });
  });
  window.addEventListener('appinstalled', () => { deferred = null; document.querySelectorAll('[data-pp-install]').forEach(b => { b.hidden = true; }); });
  document.addEventListener('click', e => {
    const b = e.target.closest('[data-pp-install]'); if (!b || !deferred) return;
    deferred.prompt(); deferred.userChoice.finally(() => { deferred = null; b.hidden = true; });
  });

  // ---- logging out forgets the saved pages that were personalised ----
  document.addEventListener('submit', e => {
    if (/\/logout$/.test(new URL(e.target.action, location.href).pathname) && navigator.serviceWorker && navigator.serviceWorker.controller) {
      navigator.serviceWorker.controller.postMessage({ type: 'clear-user' });
    }
  }, true);

  // ---- service worker ----
  if (!('serviceWorker' in navigator) || !(window.isSecureContext)) return;
  const PREFETCH = ['/recipes/', '/recipes/tips'];
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js', { scope: '/' }).then(reg => {
      const waiting = () => note(T('offline.update'), T('offline.reload'), () => { reg.waiting.postMessage({ type: 'skip-waiting' }); }, true);
      if (reg.waiting && navigator.serviceWorker.controller) waiting();
      reg.addEventListener('updatefound', () => {
        const w = reg.installing; if (!w) return;
        w.addEventListener('statechange', () => { if (w.state === 'installed' && navigator.serviceWorker.controller) waiting(); });
      });
      // save the recipe book so Cook Mode works even if you never opened it online
      navigator.serviceWorker.ready.then(r => {
        if (!navigator.onLine || (navigator.connection && navigator.connection.saveData)) return;
        navigator.serviceWorker.addEventListener('message', ev => {
          if (ev.data && ev.data.type === 'prefetched' && ev.data.fresh) note(T('offline.ready'));
        });
        if (r.active) r.active.postMessage({ type: 'prefetch', urls: PREFETCH });
      });
    }).catch(() => {});
    // reload once when an update the person accepted takes over (not on the very first install)
    const hadController = !!navigator.serviceWorker.controller;
    let reloading = false;
    navigator.serviceWorker.addEventListener('controllerchange', () => { if (!hadController || reloading) return; reloading = true; location.reload(); });
  });
})();
