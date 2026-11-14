// "Catch the facts": a small original game that appears when the connection drops or the server is unreachable.
// Move with ← → (or A/D, or by touch/mouse). Catch ✅ facts, dodge ❌ hallucinations. Disappears when you're back online.
(function () {
  let overlay, canvas, ctx, raf, running = false, items = [], score = 0, lives = 3, x = 0.5, spawnT = 0, speed = 1, best = 0;
  const keys = {};
  try { best = +localStorage.getItem('hn-best') || 0; } catch (_) {}

  function build() {
    overlay = document.createElement('div');
    overlay.id = 'hn-offline';
    overlay.innerHTML = `
      <div class="hn-card">
        <div class="hn-top"><b>${window.HN_PLAY ? '🎮 Catch the facts' : "📡 You're offline"}</b><span>Catch the ✅ facts, dodge the ❌ hallucinations. Use ← → or move the mouse.</span></div>
        <canvas width="640" height="360"></canvas>
        <div class="hn-bot"><span id="hn-score"></span><button id="hn-retry" type="button">Play again</button><span class="hn-dim">${window.HN_PLAY ? '<a href="/" style="color:#9aa0a8">← Back to Hallucinot</a>' : "We'll reconnect automatically."}</span></div>
      </div>`;
    const st = document.createElement('style');
    st.textContent = `#hn-offline{position:fixed;inset:0;background:rgba(10,11,13,.82);display:flex;align-items:center;justify-content:center;z-index:9999;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
      #hn-offline .hn-card{background:#14161a;border:1px solid #2a2e34;border-radius:16px;padding:16px;max-width:680px;width:calc(100% - 32px);color:#ececf1}
      #hn-offline .hn-top{display:flex;flex-direction:column;gap:2px;margin-bottom:10px}#hn-offline .hn-top span{color:#9aa0a8;font-size:13px}
      #hn-offline canvas{width:100%;height:auto;background:#0b0c0e;border-radius:10px;display:block;touch-action:none}
      #hn-offline .hn-bot{display:flex;gap:12px;align-items:center;margin-top:10px;font-size:14px}
      #hn-offline button{border:0;border-radius:999px;padding:6px 14px;background:#5b3fd6;color:#fff;font-weight:600;cursor:pointer}
      #hn-offline .hn-dim{color:#6b6b76;margin-left:auto;font-size:12px}`;
    document.head.appendChild(st);
    document.body.appendChild(overlay);
    canvas = overlay.querySelector('canvas'); ctx = canvas.getContext('2d');
    const move = e => { const r = canvas.getBoundingClientRect(); const cx = (e.touches ? e.touches[0].clientX : e.clientX); x = Math.min(0.95, Math.max(0.05, (cx - r.left) / r.width)); };
    canvas.addEventListener('mousemove', move); canvas.addEventListener('touchmove', e => { move(e); e.preventDefault(); }, {passive: false});
    overlay.querySelector('#hn-retry').addEventListener('click', reset);
  }
  function reset() { items = []; score = 0; lives = 3; speed = 1; spawnT = 0; x = 0.5; if (!running) { running = true; loop(); } }
  function loop() {
    if (!running) return;
    const W = canvas.width, H = canvas.height;
    if (keys.ArrowLeft || keys.a) x = Math.max(0.05, x - 0.018);
    if (keys.ArrowRight || keys.d) x = Math.min(0.95, x + 0.018);
    if (lives > 0) {
      spawnT -= 1;
      if (spawnT <= 0) { items.push({x: 0.06 + Math.random() * 0.88, y: -20, good: Math.random() < 0.6}); spawnT = Math.max(18, 48 - score); speed = 1 + score * 0.04; }
      for (const it of items) it.y += 2.2 * speed;
      const px = x * W, py = H - 34;
      items = items.filter(it => {
        const ix = it.x * W;
        if (it.y > py - 18 && it.y < py + 18 && Math.abs(ix - px) < 40) { if (it.good) score++; else lives--; return false; }
        if (it.y > H + 20) { if (it.good) lives = Math.max(0, lives); return false; }
        return true;
      });
      if (score > best) { best = score; try { localStorage.setItem('hn-best', best); } catch (_) {} }
    }
    ctx.clearRect(0, 0, W, H);
    ctx.font = '28px serif'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    for (const it of items) ctx.fillText(it.good ? '✅' : '❌', it.x * W, it.y);
    ctx.font = '40px serif'; ctx.fillText('🦖', x * W, H - 34);
    ctx.fillStyle = '#ececf1'; ctx.font = '600 16px -apple-system,sans-serif'; ctx.textAlign = 'left';
    ctx.fillText(`Facts ${score}`, 14, 22); ctx.textAlign = 'right'; ctx.fillText('❤️'.repeat(Math.max(0, lives)) + `   best ${best}`, W - 14, 22);
    if (lives <= 0) { ctx.textAlign = 'center'; ctx.font = '700 28px -apple-system,sans-serif'; ctx.fillText('Too many hallucinations!', W / 2, H / 2 - 10);
      ctx.font = '16px -apple-system,sans-serif'; ctx.fillStyle = '#9aa0a8'; ctx.fillText('Press "Play again"', W / 2, H / 2 + 22); }
    overlay.querySelector('#hn-score').textContent = `✅ ${score} facts caught`;
    raf = requestAnimationFrame(loop);
  }
  function show() { if (!overlay) build(); overlay.style.display = 'flex'; reset(); }
  function hide() { if (overlay) overlay.style.display = 'none'; running = false; cancelAnimationFrame(raf); }
  addEventListener('keydown', e => { keys[e.key] = true; if (overlay && overlay.style.display !== 'none' && ['ArrowLeft', 'ArrowRight'].includes(e.key)) e.preventDefault(); });
  addEventListener('keyup', e => { keys[e.key] = false; });

  // when to show: the browser goes offline, or our server stops answering
  let fails = 0;
  addEventListener('offline', show);
  addEventListener('online', () => { fails = 0; if (!window.HN_PLAY) hide(); });
  setInterval(async () => {
    try { const r = await fetch('/api/kb', {cache: 'no-store'}); if (!r.ok) throw 0; fails = 0; if (navigator.onLine && !window.HN_PLAY) hide(); }
    catch (_) { if (++fails >= 2) show(); }
  }, 5000);
  window.hnOfflineGame = {show, hide};   // for testing
})();
