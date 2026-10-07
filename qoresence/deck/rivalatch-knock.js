/* Mobile Glass · Knock Rivalatch — share / deep-link for the local tip.
 * Builds nothing itself: asks the deck (/api/rivalatch/knock-link) for a
 * rivalatch://knock?… URI at the checkout tip. No API key on this page.
 * Tip unknown → HOLD pill, no link (goes dark instead of lying).
 */
(function () {
  if (window.__qoreRivalatchKnock) return;
  window.__qoreRivalatchKnock = true;

  function el(tag, attrs, text) {
    var n = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) { n.setAttribute(k, attrs[k]); });
    if (text) n.textContent = text;
    return n;
  }

  var box = el('div', { id: 'qore-rivalatch-knock', 'data-knock': 'rivalatch', role: 'group', 'aria-label': 'Knock Rivalatch' });
  box.style.cssText = 'position:fixed;right:10px;bottom:calc(10px + env(safe-area-inset-bottom));z-index:40;' +
    'display:flex;gap:6px;align-items:center;font:700 11px/1 ui-monospace,monospace;letter-spacing:.04em';
  var pill = 'border-radius:999px;padding:9px 12px;border:1px solid rgba(155,231,255,.35);' +
    'background:rgba(5,6,10,.82);color:#9be7ff;text-decoration:none;cursor:pointer';
  var link = el('a', { id: 'qore-rivalatch-link', href: '#', rel: 'noopener' }, 'Knock Rivalatch');
  link.style.cssText = pill;
  var share = el('button', { id: 'qore-rivalatch-share', type: 'button' }, 'Share');
  share.style.cssText = pill + ';display:none';
  box.appendChild(link);
  box.appendChild(share);

  function hold(msg) {
    link.textContent = 'Rivalatch · HOLD';
    link.title = msg || 'local git tip unknown';
    link.removeAttribute('href');
    link.style.color = '#d7b36a';
    share.style.display = 'none';
  }

  function arm(info) {
    var uri = info.deep_link;
    var short = String(info.sha || '').slice(0, 7);
    link.textContent = 'Knock Rivalatch · ' + short;
    link.title = info.note || '';
    link.setAttribute('href', uri);
    share.style.display = '';
    share.onclick = function () {
      var text = 'Rivalatch knock — Qoresence tip ' + short + '\n\n' + uri + '\n';
      if (navigator.share) {
        navigator.share({ title: 'Knock Rivalatch', text: text }).catch(function () {});
      } else if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(uri).then(function () {
          share.textContent = 'Copied';
          setTimeout(function () { share.textContent = 'Share'; }, 1500);
        }).catch(function () {});
      }
    };
  }

  function mount() {
    if (!document.body || document.getElementById('qore-rivalatch-knock')) return;
    document.body.appendChild(box);
    fetch('/api/rivalatch/knock-link', { cache: 'no-store' })
      .then(function (r) { return r.json(); })
      .then(function (info) {
        if (info && info.ok && info.deep_link && /^rivalatch:\/\/knock\?/.test(info.deep_link)) arm(info);
        else hold(info && info.note);
      })
      .catch(function () { hold('deck unreachable'); });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount);
  else mount();
})();
