// Animated complex-network background for the "quantum" style (home page only).
(function () {
  var c = document.getElementById('bg-net');
  if (!c) return;
  var ctx = c.getContext('2d'), dpr = Math.min(window.devicePixelRatio || 1, 2);
  var reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  var W, H, nodes = [], mouse = { x: -1e4, y: -1e4 };
  function resize() {
    W = c.clientWidth; H = c.clientHeight;
    c.width = W * dpr; c.height = H * dpr; ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    var n = Math.round(Math.min(110, W * H / 9000));
    nodes = [];
    for (var i = 0; i < n; i++) nodes.push({
      x: Math.random() * W, y: Math.random() * H,
      vx: (Math.random() - .5) * .35, vy: (Math.random() - .5) * .35,
      r: Math.random() * 1.6 + .6, hue: Math.random() < .7 ? 190 : 265
    });
  }
  function step() {
    ctx.clearRect(0, 0, W, H);
    var D = 130;
    for (var i = 0; i < nodes.length; i++) {
      var a = nodes[i];
      if (!reduce) { a.x += a.vx; a.y += a.vy; }
      if (a.x < 0 || a.x > W) a.vx *= -1;
      if (a.y < 0 || a.y > H) a.vy *= -1;
      for (var j = i + 1; j < nodes.length; j++) {
        var b = nodes[j], dx = a.x - b.x, dy = a.y - b.y, d = Math.sqrt(dx * dx + dy * dy);
        if (d < D) {
          ctx.strokeStyle = 'hsla(' + a.hue + ',95%,72%,' + (1 - d / D) * .28 + ')';
          ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
        }
      }
      var md = Math.hypot(a.x - mouse.x, a.y - mouse.y), glow = md < 160 ? 1 - md / 160 : 0;
      ctx.fillStyle = 'hsla(' + a.hue + ',95%,75%,' + (.55 + glow * .45) + ')';
      ctx.shadowColor = 'hsla(' + a.hue + ',95%,70%,.9)'; ctx.shadowBlur = 8 + glow * 14;
      ctx.beginPath(); ctx.arc(a.x, a.y, a.r + glow * 2, 0, 6.283); ctx.fill(); ctx.shadowBlur = 0;
    }
    if (!reduce) requestAnimationFrame(step);
  }
  addEventListener('resize', resize);
  addEventListener('mousemove', function (e) { var r = c.getBoundingClientRect(); mouse.x = e.clientX - r.left; mouse.y = e.clientY - r.top; });
  resize(); step();
})();
