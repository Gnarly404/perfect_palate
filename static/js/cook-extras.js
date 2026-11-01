/* Perfect Palate - Cook Mode extras: keep the screen awake, hands-free voice commands, timer alarm.
 * Loaded after the recipes page script, so it can call cNav(), doTimer() and read curStep.
 * Everything degrades quietly: no Wake Lock -> a note; no SpeechRecognition -> the button explains why.
 */
(function () {
  'use strict';
  const T = (k, v) => PPI18N.t(k, v);
  const $ = id => document.getElementById(id);

  // ---------- Screen Wake Lock ----------
  let lock = null, inCook = false;
  async function acquireLock() {
    if (!inCook || !('wakeLock' in navigator) || document.visibilityState !== 'visible') return;
    try {
      lock = await navigator.wakeLock.request('screen');
      lock.addEventListener('release', () => { lock = null; paintAwake(); });
    } catch (e) { lock = null; }
    paintAwake();
  }
  function releaseLock() { if (lock) { lock.release().catch(() => {}); lock = null; } paintAwake(); }
  function paintAwake() {
    const el = $('cookAwake'); if (!el) return;
    const supported = 'wakeLock' in navigator;
    el.hidden = false;
    el.classList.toggle('on', !!lock);
    el.textContent = supported ? (lock ? '☀ ' + T('cook.awake') : '') : T('cook.awakeNo');
    el.hidden = supported && !lock;
  }
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') acquireLock(); });

  // ---------- Alarm (audible when your hands are covered in flour) ----------
  let ctx = null;
  function prepAudio() {
    try { ctx = ctx || new (window.AudioContext || window.webkitAudioContext)(); if (ctx.state === 'suspended') ctx.resume(); } catch (e) { ctx = null; }
  }
  function alarm() {
    try { if (navigator.vibrate) navigator.vibrate([300, 150, 300, 150, 300]); } catch (e) {}
    if (!ctx) return;
    [0, 0.35, 0.7].forEach(at => {
      const o = ctx.createOscillator(), g = ctx.createGain();
      o.type = 'sine'; o.frequency.value = 880;
      g.gain.setValueAtTime(0.0001, ctx.currentTime + at);
      g.gain.exponentialRampToValueAtTime(0.25, ctx.currentTime + at + 0.03);
      g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + at + 0.28);
      o.connect(g); g.connect(ctx.destination); o.start(ctx.currentTime + at); o.stop(ctx.currentTime + at + 0.3);
    });
  }

  // ---------- Voice commands ----------
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  let rec = null, wanted = false, restartTimer = null, failures = 0;
  const msg = (text, bad) => { const m = $('cookVoiceMsg'); if (m) { m.textContent = text || ''; m.classList.toggle('bad', !!bad); } };
  function paintVoice() {
    const b = $('cookVoice'); if (!b) return;
    b.classList.toggle('on', wanted);
    b.setAttribute('aria-pressed', wanted ? 'true' : 'false');
    b.innerHTML = '<i class="fa-solid fa-microphone' + (wanted ? '' : '-slash') + '" aria-hidden="true"></i> ' + (wanted ? T('cook.voiceStop') : T('cook.voice'));
  }
  function speakStep() {
    if (!window.speechSynthesis || !curCook) return;
    const text = curCookSteps[curStep]; if (!text) return;
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = PPI18N.lang() === 'sw' ? 'sw-KE' : 'en-KE';
    // do not let the recogniser hear the app reading the step out loud
    try { rec && rec.stop(); } catch (e) {}
    u.onend = u.onerror = () => { if (wanted) startRec(); };
    window.speechSynthesis.speak(u);
  }
  function run(cmd) {
    if (!curCook) return;
    if (cmd === 'next') { if (curStep >= curCookSteps.length - 1) { msg(T('cook.last')); return; } cNav(1); }
    else if (cmd === 'back') { if (curStep <= 0) { msg(T('cook.first')); return; } cNav(-1); }
    else if (cmd === 'repeat') speakStep();
    else if (cmd === 'timer') { const el = $('tm' + curStep); if (!el) { msg(T('cook.noTimer')); return; } if (!el.classList.contains('run')) el.click(); }
    else if (cmd === 'stop-timer') { const el = $('tm' + curStep); if (el && el.classList.contains('run')) el.click(); }
  }
  function startRec() {
    if (!wanted || !SR || !inCook) return;
    clearTimeout(restartTimer);
    rec = new SR();
    rec.continuous = true; rec.interimResults = false; rec.maxAlternatives = 3;
    rec.lang = PPI18N.lang() === 'sw' ? 'sw-KE' : 'en-KE';
    rec.onresult = e => {
      failures = 0;
      for (let i = e.resultIndex; i < e.results.length; i++) {
        if (!e.results[i].isFinal) continue;
        for (let a = 0; a < e.results[i].length; a++) {
          const cmd = PPTools.matchCommand(e.results[i][a].transcript);
          if (cmd) { msg(T('cook.voiceHeard', { t: e.results[i][a].transcript.trim() })); run(cmd); break; }
        }
      }
    };
    rec.onerror = e => {
      if (e.error === 'not-allowed' || e.error === 'service-not-allowed') { wanted = false; msg(T('cook.voiceDenied'), true); paintVoice(); }
      else if (e.error === 'network') { wanted = false; msg(T('cook.voiceNet'), true); paintVoice(); }
    };
    rec.onend = () => { // the browser ends sessions every so often; keep listening unless turned off
      if (!wanted || !inCook) return;
      failures++;
      restartTimer = setTimeout(startRec, Math.min(4000, 250 * failures));
    };
    try { rec.start(); msg(T('cook.voiceHint')); } catch (e) { /* already started */ }
  }
  function toggleVoice() {
    if (!SR) { msg(T('cook.voiceNo'), true); return; }
    if (!navigator.onLine) { msg(T('cook.voiceNet'), true); return; }
    wanted = !wanted; failures = 0; paintVoice();
    if (wanted) { prepAudio(); startRec(); } else { stopRec(); msg(''); }
  }
  function stopRec() { clearTimeout(restartTimer); try { rec && rec.stop(); } catch (e) {} rec = null; }

  window.CookExtras = {
    enter() {
      inCook = true; prepAudio(); acquireLock(); paintVoice(); paintAwake();
      const b = $('cookVoice'); if (b && !b._wired) { b._wired = true; b.addEventListener('click', toggleVoice); }
      if (!SR && b) b.title = T('cook.voiceNo');
    },
    exit() { if (!inCook) return; inCook = false; releaseLock(); wanted = false; stopRec(); paintVoice(); msg(''); },
    alarm,
  };
})();
