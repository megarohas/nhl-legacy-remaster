// 3D-просмотр сетки (WebGL 1, без библиотек) и развёртка UV: вращение мышью, колесо — масштаб.
'use strict';
const View3D = (() => {
  const VS = `attribute vec3 p; attribute vec3 n; uniform mat4 mvp; uniform mat4 mv; varying vec3 vn;
    void main(){ gl_Position = mvp*vec4(p,1.0); vn = (mv*vec4(n,0.0)).xyz; }`;
  const FS = `precision mediump float; varying vec3 vn; uniform vec3 col;
    void main(){ vec3 N = normalize(vn); float d = abs(dot(N, normalize(vec3(0.4,0.6,1.0))));
      gl_FragColor = vec4(col*(0.25+0.75*d),1.0); }`;
  function sh(gl, type, src) { const s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s); return s; }
  function mul(a, b) { const o = new Float32Array(16); for (let i = 0; i < 4; i++) for (let j = 0; j < 4; j++) { let s = 0; for (let k = 0; k < 4; k++) s += a[k * 4 + j] * b[i * 4 + k]; o[i * 4 + j] = s; } return o; }
  function persp(f, a, n, fa) { const t = 1 / Math.tan(f / 2); return new Float32Array([t / a, 0, 0, 0, 0, t, 0, 0, 0, 0, (fa + n) / (n - fa), -1, 0, 0, 2 * fa * n / (n - fa), 0]); }
  function rotY(r) { const c = Math.cos(r), s = Math.sin(r); return new Float32Array([c, 0, -s, 0, 0, 1, 0, 0, s, 0, c, 0, 0, 0, 0, 1]); }
  function rotX(r) { const c = Math.cos(r), s = Math.sin(r); return new Float32Array([1, 0, 0, 0, 0, c, s, 0, 0, -s, c, 0, 0, 0, 0, 1]); }
  function trans(x, y, z) { return new Float32Array([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, x, y, z, 1]); }
  function normals(pos, idx) {
    const n = new Float32Array(pos.length);
    for (let i = 0; i < idx.length; i += 3) {
      const a = idx[i] * 3, b = idx[i + 1] * 3, c = idx[i + 2] * 3;
      const ux = pos[b] - pos[a], uy = pos[b + 1] - pos[a + 1], uz = pos[b + 2] - pos[a + 2];
      const vx = pos[c] - pos[a], vy = pos[c + 1] - pos[a + 1], vz = pos[c + 2] - pos[a + 2];
      const nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
      for (const k of [a, b, c]) { n[k] += nx; n[k + 1] += ny; n[k + 2] += nz; }
    }
    return n;
  }
  function mount(canvas, geom) {
    const gl = canvas.getContext('webgl', { antialias: true });
    if (!gl) { canvas.replaceWith(document.createTextNode('WebGL недоступен')); return; }
    const ext = gl.getExtension('OES_element_index_uint');
    const prog = gl.createProgram();
    gl.attachShader(prog, sh(gl, gl.VERTEX_SHADER, VS)); gl.attachShader(prog, sh(gl, gl.FRAGMENT_SHADER, FS));
    gl.linkProgram(prog); gl.useProgram(prog);
    let mn = [1e9, 1e9, 1e9], mx = [-1e9, -1e9, -1e9];
    const parts = geom.subs.map(s => {
      for (let i = 0; i < s.pos.length; i += 3) for (let k = 0; k < 3; k++) { mn[k] = Math.min(mn[k], s.pos[i + k]); mx[k] = Math.max(mx[k], s.pos[i + k]); }
      const pb = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, pb); gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(s.pos), gl.STATIC_DRAW);
      const nb = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, nb); gl.bufferData(gl.ARRAY_BUFFER, normals(s.pos, s.idx), gl.STATIC_DRAW);
      const ib = gl.createBuffer(); gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, ib);
      const big = s.nv > 65535 && ext;
      gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, big ? new Uint32Array(s.idx) : new Uint16Array(s.idx), gl.STATIC_DRAW);
      return { pb, nb, ib, n: s.idx.length, type: big ? gl.UNSIGNED_INT : gl.UNSIGNED_SHORT };
    });
    const c = [(mn[0] + mx[0]) / 2, (mn[1] + mx[1]) / 2, (mn[2] + mx[2]) / 2];
    const r = Math.max(mx[0] - mn[0], mx[1] - mn[1], mx[2] - mn[2]) || 1;
    const st = { yaw: 0.6, pitch: 0.25, dist: r * 1.9 };
    const lp = gl.getAttribLocation(prog, 'p'), ln = gl.getAttribLocation(prog, 'n');
    const um = gl.getUniformLocation(prog, 'mvp'), uv = gl.getUniformLocation(prog, 'mv'), uc = gl.getUniformLocation(prog, 'col');
    const cols = [[0.78, 0.8, 0.84], [0.55, 0.75, 0.95], [0.95, 0.7, 0.5], [0.6, 0.9, 0.6]];
    function draw() {
      const w = canvas.clientWidth, h = canvas.clientHeight;
      if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
      gl.viewport(0, 0, w, h); gl.clearColor(0.05, 0.06, 0.07, 1); gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
      gl.enable(gl.DEPTH_TEST);
      const mv = mul(trans(0, 0, -st.dist), mul(rotX(st.pitch), mul(rotY(st.yaw), trans(-c[0], -c[1], -c[2]))));
      const mvp = mul(persp(0.8, w / h, r * 0.02, r * 20), mv);
      gl.uniformMatrix4fv(um, false, mvp); gl.uniformMatrix4fv(uv, false, mv);
      parts.forEach((p, i) => {
        gl.uniform3fv(uc, cols[i % cols.length]);
        gl.bindBuffer(gl.ARRAY_BUFFER, p.pb); gl.enableVertexAttribArray(lp); gl.vertexAttribPointer(lp, 3, gl.FLOAT, false, 0, 0);
        gl.bindBuffer(gl.ARRAY_BUFFER, p.nb); gl.enableVertexAttribArray(ln); gl.vertexAttribPointer(ln, 3, gl.FLOAT, false, 0, 0);
        gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, p.ib); gl.drawElements(gl.TRIANGLES, p.n, p.type, 0);
      });
    }
    let drag = null;
    canvas.addEventListener('mousedown', e => { drag = [e.clientX, e.clientY]; });
    window.addEventListener('mouseup', () => { drag = null; });
    window.addEventListener('mousemove', e => {
      if (!drag) return;
      st.yaw += (e.clientX - drag[0]) * 0.01; st.pitch = Math.max(-1.5, Math.min(1.5, st.pitch + (e.clientY - drag[1]) * 0.01));
      drag = [e.clientX, e.clientY]; draw();
    });
    canvas.addEventListener('wheel', e => { e.preventDefault(); st.dist *= e.deltaY < 0 ? 0.9 : 1.1; draw(); }, { passive: false });
    new ResizeObserver(draw).observe(canvas);
    draw();
  }
  function uvLayout(canvas, geom, imgUrl) {
    const S = 512; canvas.width = S; canvas.height = S;
    const g = canvas.getContext('2d');
    const lines = () => {
      g.strokeStyle = 'rgba(255,210,60,0.75)'; g.lineWidth = 0.6;
      for (const s of geom.subs) {
        if (!s.uv.length) continue;
        g.beginPath();
        for (let i = 0; i < s.idx.length; i += 3) {
          const a = s.idx[i] * 2, b = s.idx[i + 1] * 2, c = s.idx[i + 2] * 2;
          g.moveTo(s.uv[a] * S, s.uv[a + 1] * S); g.lineTo(s.uv[b] * S, s.uv[b + 1] * S); g.lineTo(s.uv[c] * S, s.uv[c + 1] * S); g.closePath();
        }
        g.stroke();
      }
    };
    g.fillStyle = '#1b1f26'; g.fillRect(0, 0, S, S);
    if (imgUrl) { const im = new Image(); im.onload = () => { g.drawImage(im, 0, 0, S, S); lines(); }; im.onerror = lines; im.src = imgUrl; }
    else lines();
  }
  return { mount, uvLayout };
})();
