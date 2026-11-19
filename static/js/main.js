(function () {
  // ---- mobile nav
  var toggle = document.querySelector('.nav-toggle');
  var nav = document.querySelector('.nav nav');
  if (toggle && nav) toggle.addEventListener('click', function () {
    var open = nav.classList.toggle('open');
    toggle.setAttribute('aria-expanded', open);
  });

  // ---- theme
  var tbtn = document.querySelector('.theme-toggle');
  if (tbtn) tbtn.addEventListener('click', function () {
    var root = document.documentElement;
    var cur = root.dataset.theme ||
      (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    var next = cur === 'dark' ? 'light' : 'dark';
    root.dataset.theme = next;
    try { localStorage.setItem('theme', next); } catch (e) {}
  });

  // ---- toast
  function toast(msg) {
    var t = document.createElement('div');
    t.className = 'toast'; t.textContent = msg; document.body.appendChild(t);
    requestAnimationFrame(function () { t.classList.add('show'); });
    setTimeout(function () { t.classList.remove('show'); setTimeout(function () { t.remove(); }, 300); }, 1800);
  }

  // ---- copy BibTeX
  document.addEventListener('click', function (e) {
    var b = e.target.closest('.cite');
    if (!b) return;
    var txt = b.getAttribute('data-bib');
    var done = function () { b.classList.add('copied'); b.textContent = 'Copied'; toast('BibTeX copied to clipboard');
      setTimeout(function () { b.classList.remove('copied'); b.textContent = 'Cite'; }, 1600); };
    if (navigator.clipboard) navigator.clipboard.writeText(txt).then(done, function () { window.prompt('BibTeX', txt); });
    else window.prompt('BibTeX', txt);
  });

  // ---- publication filtering
  var search = document.getElementById('pub-search');
  var filters = document.querySelectorAll('.filter');
  if (!search) return;
  var current = 'all';
  function apply() {
    var q = search.value.trim().toLowerCase().split(/\s+/).filter(Boolean);
    var any = false;
    document.querySelectorAll('.year-group').forEach(function (g) {
      var vis = 0;
      g.querySelectorAll('.pub').forEach(function (p) {
        var s = p.getAttribute('data-search');
        var ok = (current === 'all' || p.dataset.type === current) && q.every(function (w) { return s.indexOf(w) !== -1; });
        p.hidden = !ok; if (ok) vis++;
      });
      g.hidden = vis === 0; if (vis) any = true;
    });
    document.getElementById('no-results').hidden = any;
  }
  filters.forEach(function (f) {
    f.addEventListener('click', function () {
      filters.forEach(function (x) { x.classList.remove('active'); });
      f.classList.add('active'); current = f.dataset.filter; apply();
    });
  });
  search.addEventListener('input', apply);
  var params = new URLSearchParams(location.search);
  if (params.get('q')) { search.value = params.get('q'); apply(); }
})();

// ---- click-to-play YouTube (no YouTube cookies until the visitor presses play)
document.addEventListener('click', function (e) {
  var f = e.target.closest('.video-facade');
  if (!f) return;
  var box = f.parentElement, id = box.getAttribute('data-yt');
  var ifr = document.createElement('iframe');
  ifr.src = 'https://www.youtube-nocookie.com/embed/' + encodeURIComponent(id) + '?autoplay=1&rel=0';
  ifr.title = f.getAttribute('aria-label') || 'Video';
  ifr.allow = 'accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share';
  ifr.allowFullscreen = true;
  box.innerHTML = ''; box.appendChild(ifr);
});
