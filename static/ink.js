/**
 * Ink Flow Field — Vanilla JS Port
 * Using component defaults.
 */

// Grid resolutions
const SIM_RES = 128;
const DYE_RES = 512;
const PRESSURE_ITERATIONS = 20;
const PRESSURE_DECAY = 0.8;
const VELOCITY_DISSIPATION = 0.2;
const CURL_AT_50 = 30;
const INJECT_RATE = 4.5;
const SEEDS = [
    [0.28, 0.62, 140, 60],
    [0.66, 0.38, -120, 90],
    [0.5, 0.5, 40, -140],
];
const DPR_CAP = 1.5;
const MAX_COLORS = 5;
const DEFAULT_COLORS = ["#E0E7FF", "#C7D2FE", "#818CF8", "#4F46E5", "#3730A3"]; // Light mode B2B SaaS palette

const GL_RGBA16F = 0x881a;
const GL_HALF_FLOAT = 0x140b;
const GL_HALF_FLOAT_OES = 0x8d61;

const VERT = `
precision highp float;
attribute vec2 aPos;
uniform vec2 uTexel;
varying vec2 vUv;
varying vec2 vL;
varying vec2 vR;
varying vec2 vT;
varying vec2 vB;
void main() {
    vUv = aPos * 0.5 + 0.5;
    vL = vUv - vec2(uTexel.x, 0.0);
    vR = vUv + vec2(uTexel.x, 0.0);
    vT = vUv + vec2(0.0, uTexel.y);
    vB = vUv - vec2(0.0, uTexel.y);
    gl_Position = vec4(aPos, 0.0, 1.0);
}
`;

const FRAG_ADVECT = `
precision highp float;
uniform sampler2D uVel;
uniform sampler2D uSrc;
uniform vec2 uTexel;
uniform vec2 uTexelSrc;
uniform float uDt;
uniform float uDiss;
varying vec2 vUv;

#ifdef MANUAL_FILTERING
vec4 bilerp(sampler2D s, vec2 uv, vec2 tsize) {
    vec2 st = uv / tsize - 0.5;
    vec2 iuv = floor(st);
    vec2 fuv = fract(st);
    vec4 a = texture2D(s, (iuv + vec2(0.5, 0.5)) * tsize);
    vec4 b = texture2D(s, (iuv + vec2(1.5, 0.5)) * tsize);
    vec4 c = texture2D(s, (iuv + vec2(0.5, 1.5)) * tsize);
    vec4 d = texture2D(s, (iuv + vec2(1.5, 1.5)) * tsize);
    return mix(mix(a, b, fuv.x), mix(c, d, fuv.x), fuv.y);
}
#endif

void main() {
    vec2 coord = vUv - uDt * texture2D(uVel, vUv).xy * uTexel;
    vec2 halfTexel = uTexelSrc * 0.5;
    coord = clamp(coord, halfTexel, 1.0 - halfTexel);
#ifdef MANUAL_FILTERING
    vec4 src = bilerp(uSrc, coord, uTexelSrc);
#else
    vec4 src = texture2D(uSrc, coord);
#endif
    gl_FragColor = src / (1.0 + uDiss * uDt);
}
`;

const FRAG_DIVERGENCE = `
precision highp float;
uniform sampler2D uVel;
varying vec2 vUv;
varying vec2 vL;
varying vec2 vR;
varying vec2 vT;
varying vec2 vB;
void main() {
    float l = texture2D(uVel, vL).x;
    float r = texture2D(uVel, vR).x;
    float t = texture2D(uVel, vT).y;
    float b = texture2D(uVel, vB).y;
    vec2 c = texture2D(uVel, vUv).xy;
    if (vL.x < 0.0) l = -c.x;
    if (vR.x > 1.0) r = -c.x;
    if (vT.y > 1.0) t = -c.y;
    if (vB.y < 0.0) b = -c.y;
    gl_FragColor = vec4(0.5 * (r - l + t - b), 0.0, 0.0, 1.0);
}
`;

const FRAG_CURL = `
precision highp float;
uniform sampler2D uVel;
varying vec2 vL;
varying vec2 vR;
varying vec2 vT;
varying vec2 vB;
void main() {
    float l = texture2D(uVel, vL).y;
    float r = texture2D(uVel, vR).y;
    float t = texture2D(uVel, vT).x;
    float b = texture2D(uVel, vB).x;
    gl_FragColor = vec4(0.5 * (r - l - t + b), 0.0, 0.0, 1.0);
}
`;

const FRAG_VORTICITY = `
precision highp float;
uniform sampler2D uVel;
uniform sampler2D uCurl;
uniform float uCurlAmt;
uniform float uDt;
varying vec2 vUv;
varying vec2 vL;
varying vec2 vR;
varying vec2 vT;
varying vec2 vB;
void main() {
    float l = texture2D(uCurl, vL).x;
    float r = texture2D(uCurl, vR).x;
    float t = texture2D(uCurl, vT).x;
    float b = texture2D(uCurl, vB).x;
    float c = texture2D(uCurl, vUv).x;

    vec2 force = 0.5 * vec2(abs(t) - abs(b), abs(r) - abs(l));
    force /= max(length(force), 1e-4);
    force *= uCurlAmt * c;
    force.y *= -1.0;

    vec2 vel = texture2D(uVel, vUv).xy + force * uDt;
    gl_FragColor = vec4(clamp(vel, -1000.0, 1000.0), 0.0, 1.0);
}
`;

const FRAG_PRESSURE = `
precision highp float;
uniform sampler2D uPressure;
uniform sampler2D uDivergence;
varying vec2 vUv;
varying vec2 vL;
varying vec2 vR;
varying vec2 vT;
varying vec2 vB;
void main() {
    float l = texture2D(uPressure, vL).x;
    float r = texture2D(uPressure, vR).x;
    float t = texture2D(uPressure, vT).x;
    float b = texture2D(uPressure, vB).x;
    float div = texture2D(uDivergence, vUv).x;
    gl_FragColor = vec4((l + r + t + b - div) * 0.25, 0.0, 0.0, 1.0);
}
`;

const FRAG_GRADIENT = `
precision highp float;
uniform sampler2D uPressure;
uniform sampler2D uVel;
varying vec2 vUv;
varying vec2 vL;
varying vec2 vR;
varying vec2 vT;
varying vec2 vB;
void main() {
    float l = texture2D(uPressure, vL).x;
    float r = texture2D(uPressure, vR).x;
    float t = texture2D(uPressure, vT).x;
    float b = texture2D(uPressure, vB).x;
    vec2 vel = texture2D(uVel, vUv).xy - vec2(r - l, t - b);
    gl_FragColor = vec4(vel, 0.0, 1.0);
}
`;

const FRAG_CLEAR = `
precision highp float;
uniform sampler2D uTex;
uniform float uValue;
varying vec2 vUv;
void main() {
    gl_FragColor = uValue * texture2D(uTex, vUv);
}
`;

const FRAG_SPLAT = `
precision highp float;
uniform sampler2D uTarget;
uniform float uAspect;
uniform vec3 uColor;
uniform vec2 uPoint;
uniform float uRadius;
varying vec2 vUv;
void main() {
    vec2 p = vUv - uPoint;
    p.x *= uAspect;
    vec3 splat = exp(-dot(p, p) / uRadius) * uColor;
    gl_FragColor = vec4(texture2D(uTarget, vUv).xyz + splat, 1.0);
}
`;

const FRAG_DISPLAY = `
precision highp float;
uniform sampler2D uTex;
uniform float uGain;
varying vec2 vUv;
void main() {
    vec3 c = texture2D(uTex, vUv).rgb * uGain;
    c = c / (1.0 + c * 0.8);
    float a = clamp(max(c.r, max(c.g, c.b)), 0.0, 1.0);
    gl_FragColor = vec4(c, a);
}
`;

function parseColor(input) {
    if (!input) return [0, 0, 0];
    const s = input.trim();
    const fn = s.match(/rgba?\(([^)]+)\)/i);
    if (fn) {
        const p = fn[1].split(",").map((v) => parseFloat(v.trim()));
        return [(p[0] || 0) / 255, (p[1] || 0) / 255, (p[2] || 0) / 255];
    }
    let h = s.replace("#", "");
    if (h.length === 3 || h.length === 4) {
        h = h.split("").map((c) => c + c).join("");
    }
    h = h.padEnd(6, "0");
    return [
        parseInt(h.slice(0, 2), 16) / 255,
        parseInt(h.slice(2, 4), 16) / 255,
        parseInt(h.slice(4, 6), 16) / 255,
    ];
}

function compile(gl, type, src) {
    const sh = gl.createShader(type);
    if (!sh) return null;
    gl.shaderSource(sh, src);
    gl.compileShader(sh);
    if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
        console.warn("InkFlowField shader:", gl.getShaderInfoLog(sh));
    }
    return sh;
}

function makePass(gl, frag, names, defines) {
    const vs = compile(gl, gl.VERTEX_SHADER, VERT);
    const fs = compile(gl, gl.FRAGMENT_SHADER, defines + frag);
    const prog = gl.createProgram();
    if (!vs || !fs || !prog) return null;
    gl.attachShader(prog, vs);
    gl.attachShader(prog, fs);
    gl.bindAttribLocation(prog, 0, "aPos");
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
        console.warn("InkFlowField link:", gl.getProgramInfoLog(prog));
        return null;
    }
    const u = {};
    for (let i = 0; i < names.length; i++) {
        u[names[i]] = gl.getUniformLocation(prog, names[i]);
    }
    return { prog, u };
}

function makeTarget(gl, w, h, fmt) {
    const tex = gl.createTexture();
    const fbo = gl.createFramebuffer();
    if (!tex || !fbo) return null;
    gl.bindTexture(gl.TEXTURE_2D, tex);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, fmt.filter);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, fmt.filter);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    gl.texImage2D(gl.TEXTURE_2D, 0, fmt.internal, w, h, 0, fmt.format, fmt.type, null);
    gl.bindFramebuffer(gl.FRAMEBUFFER, fbo);
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, tex, 0);
    gl.viewport(0, 0, w, h);
    gl.clearColor(0, 0, 0, 1);
    gl.clear(gl.COLOR_BUFFER_BIT);
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    return { tex, fbo, w, h, texelX: 1 / w, texelY: 1 / h };
}

function makeDouble(gl, w, h, fmt) {
    const a = makeTarget(gl, w, h, fmt);
    const b = makeTarget(gl, w, h, fmt);
    if (!a || !b) return null;
    return {
        read: a,
        write: b,
        swap: function () {
            const t = this.read;
            this.read = this.write;
            this.write = t;
        },
    };
}

class InkFlowField {
    constructor(hostElement, options = {}) {
        this.host = hostElement;
        
        // Settings
        this.colors = options.colors || DEFAULT_COLORS;
        this.speed = options.speed ?? 99;
        this.dissipation = options.dissipation ?? 50;
        this.swirl = options.swirl ?? 0;
        this.drift = options.drift ?? 21;
        this.reach = options.cursor?.reach ?? 35;
        this.force = options.cursor?.force ?? 60;

        // Container setup
        this.host.style.position = 'absolute';
        this.host.style.inset = '0';
        this.host.style.overflow = 'hidden';
        this.host.style.pointerEvents = 'auto'; // allow interaction
        this.host.style.zIndex = '0';

        this.canvas = document.createElement("canvas");
        this.canvas.style.position = "absolute";
        this.canvas.style.inset = "0";
        this.canvas.style.width = "100%";
        this.canvas.style.height = "100%";
        this.canvas.style.display = "block";
        this.host.appendChild(this.canvas);

        this.pointer = { x: 0.5, y: 0.5, dx: 0, dy: 0, down: 0, moved: 0 };
        this.raf = 0;
        
        this.initGL();
        this.bindEvents();
    }

    initGL() {
        const glOpts = {
            alpha: true,
            antialias: false,
            premultipliedAlpha: true,
            depth: false,
            stencil: false,
            powerPreference: "high-performance",
        };

        let isGL2 = true;
        let gl = this.canvas.getContext("webgl2", glOpts);
        if (!gl) {
            isGL2 = false;
            gl = this.canvas.getContext("webgl", glOpts);
        }
        if (!gl) return;
        this.gl = gl;

        let linear = false;
        let renderable = false;
        if (isGL2) {
            renderable = !!gl.getExtension("EXT_color_buffer_float");
            if (!renderable) renderable = !!gl.getExtension("EXT_color_buffer_half_float");
            linear = !!gl.getExtension("OES_texture_float_linear") || renderable;
        } else {
            renderable =
                !!gl.getExtension("OES_texture_half_float") &&
                !!gl.getExtension("EXT_color_buffer_half_float");
            linear = !!gl.getExtension("OES_texture_half_float_linear");
        }
        if (!renderable) {
            console.warn("InkFlowField: no renderable half-float target");
            return;
        }

        const fmt = {
            internal: isGL2 ? GL_RGBA16F : gl.RGBA,
            format: gl.RGBA,
            type: isGL2 ? GL_HALF_FLOAT : GL_HALF_FLOAT_OES,
            filter: linear ? gl.LINEAR : gl.NEAREST,
        };
        const defines = linear ? "" : "#define MANUAL_FILTERING\n";
        this.fmt = fmt;

        this.advect = makePass(gl, FRAG_ADVECT, ["uVel", "uSrc", "uTexel", "uTexelSrc", "uDt", "uDiss"], defines);
        this.divergence = makePass(gl, FRAG_DIVERGENCE, ["uVel", "uTexel"], "");
        this.curl = makePass(gl, FRAG_CURL, ["uVel", "uTexel"], "");
        this.vorticity = makePass(gl, FRAG_VORTICITY, ["uVel", "uCurl", "uCurlAmt", "uDt", "uTexel"], "");
        this.pressure = makePass(gl, FRAG_PRESSURE, ["uPressure", "uDivergence", "uTexel"], "");
        this.gradient = makePass(gl, FRAG_GRADIENT, ["uPressure", "uVel", "uTexel"], "");
        this.clearPass = makePass(gl, FRAG_CLEAR, ["uTex", "uValue", "uTexel"], "");
        this.splat = makePass(gl, FRAG_SPLAT, ["uTarget", "uAspect", "uColor", "uPoint", "uRadius", "uTexel"], "");
        this.display = makePass(gl, FRAG_DISPLAY, ["uTex", "uGain", "uTexel"], "");

        if (!this.advect || !this.display) return;

        this.quad = gl.createBuffer();
        gl.bindBuffer(gl.ARRAY_BUFFER, this.quad);
        gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
        gl.enableVertexAttribArray(0);
        gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);

        gl.disable(gl.BLEND);
        gl.disable(gl.DEPTH_TEST);

        this.aspect = 1;
        this.built = "";
        
        this.resize();
        this.ro = new ResizeObserver(() => this.resize());
        this.ro.observe(this.canvas);

        this.clock = 0;
        this.colorPhase = 0;
        this.seeded = false;
        this.ax = 0.5;
        this.ay = 0.5;
        this.lastTime = performance.now();
        
        this.frame = this.frame.bind(this);
        this.raf = requestAnimationFrame(this.frame);
    }

    blit(target) {
        const gl = this.gl;
        if (target) {
            gl.viewport(0, 0, target.w, target.h);
            gl.bindFramebuffer(gl.FRAMEBUFFER, target.fbo);
        } else {
            gl.viewport(0, 0, this.canvas.width, this.canvas.height);
            gl.bindFramebuffer(gl.FRAMEBUFFER, null);
        }
        gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    }

    bindTex(tex, unit) {
        this.gl.activeTexture(this.gl.TEXTURE0 + unit);
        this.gl.bindTexture(this.gl.TEXTURE_2D, tex);
        return unit;
    }

    dispose() {
        if(!this.gl) return;
        const all = [
            this.vel?.read, this.vel?.write,
            this.dye?.read, this.dye?.write,
            this.prs?.read, this.prs?.write,
            this.div, this.crl
        ];
        for (const t of all) {
            if (!t) continue;
            this.gl.deleteTexture(t.tex);
            this.gl.deleteFramebuffer(t.fbo);
        }
        this.vel = this.dye = this.prs = null;
        this.div = this.crl = null;
    }

    buildTargets(w, h) {
        const key = w + "x" + h;
        if (key === this.built) return;
        this.dispose();
        this.aspect = w / Math.max(1, h);
        const simW = this.aspect >= 1 ? Math.round(SIM_RES * this.aspect) : SIM_RES;
        const simH = this.aspect >= 1 ? SIM_RES : Math.round(SIM_RES / this.aspect);
        const dyeW = this.aspect >= 1 ? Math.round(DYE_RES * this.aspect) : DYE_RES;
        const dyeH = this.aspect >= 1 ? DYE_RES : Math.round(DYE_RES / this.aspect);
        
        this.vel = makeDouble(this.gl, simW, simH, this.fmt);
        this.dye = makeDouble(this.gl, dyeW, dyeH, this.fmt);
        this.prs = makeDouble(this.gl, simW, simH, this.fmt);
        this.div = makeTarget(this.gl, simW, simH, this.fmt);
        this.crl = makeTarget(this.gl, simW, simH, this.fmt);
        this.built = key;
    }

    resize() {
        const dpr = Math.min(window.devicePixelRatio || 1, DPR_CAP);
        const cssW = this.canvas.clientWidth || this.host.clientWidth || 0;
        const cssH = this.canvas.clientHeight || this.host.clientHeight || 0;
        this.cssW = cssW;
        this.cssH = cssH;
        const w = Math.max(1, Math.round(cssW * dpr));
        const h = Math.max(1, Math.round(cssH * dpr));
        if (this.canvas.width !== w || this.canvas.height !== h) {
            this.canvas.width = w;
            this.canvas.height = h;
        }
        this.buildTargets(w, h);
    }

    bindEvents() {
        const host = this.host;
        this.onMove = (e) => {
            const r = host.getBoundingClientRect();
            const w = host.offsetWidth || 1;
            const h = host.offsetHeight || 1;
            const nx = (e.clientX - r.left) / Math.max(1, r.width);
            const ny = 1 - (e.clientY - r.top) / Math.max(1, r.height);
            if (this.pointer.moved) {
                this.pointer.dx += (nx - this.pointer.x) * w;
                this.pointer.dy += (ny - this.pointer.y) * h;
            }
            this.pointer.x = nx;
            this.pointer.y = ny;
            this.pointer.moved = 1;
        };
        this.onLeave = () => {
            this.pointer.moved = 0;
            this.pointer.down = 0;
        };
        this.onDown = () => { this.pointer.down = 1; };
        this.onUp = () => { this.pointer.down = 0; };
        
        host.addEventListener("pointermove", this.onMove);
        host.addEventListener("pointerleave", this.onLeave);
        host.addEventListener("pointerdown", this.onDown);
        host.addEventListener("pointercancel", this.onUp);
        window.addEventListener("pointerup", this.onUp);
    }

    doSplat(px, py, fx, fy, col, radius, ink) {
        if (!this.vel || !this.dye || !this.splat) return;
        const gl = this.gl;
        
        gl.useProgram(this.splat.prog);
        gl.uniform1f(this.splat.u.uAspect, this.aspect);
        gl.uniform2f(this.splat.u.uPoint, px, py);
        gl.uniform1f(this.splat.u.uRadius, radius);

        gl.uniform1i(this.splat.u.uTarget, this.bindTex(this.vel.read.tex, 0));
        gl.uniform3f(this.splat.u.uColor, fx, fy, 0);
        this.blit(this.vel.write);
        this.vel.swap();

        gl.uniform1i(this.splat.u.uTarget, this.bindTex(this.dye.read.tex, 0));
        gl.uniform3f(this.splat.u.uColor, col[0] * ink, col[1] * ink, col[2] * ink);
        this.blit(this.dye.write);
        this.dye.swap();
    }

    frame(now) {
        this.raf = requestAnimationFrame(this.frame);
        const dtReal = Math.min((now - this.lastTime) / 1000, 1 / 30);
        this.lastTime = now;

        if (this.cssW <= 0 || this.cssH <= 0) {
            this.resize();
            if (this.cssW <= 0 || this.cssH <= 0) return;
        }
        if (!this.vel || !this.dye || !this.prs || !this.div || !this.crl) return;

        const gl = this.gl;
        const scale = Math.max(0, this.speed) / 50;
        const dt = dtReal * scale;
        this.clock += dt;

        const pal = this.colors;
        this.colorPhase += dt * 0.25;
        const pick = (t) => {
            const i = Math.floor(Math.abs(t) * pal.length) % pal.length;
            const c = parseColor(pal[i]);
            return [c[0], c[1], c[2]];
        };

        const r = 0.008 + (Math.max(0, this.reach) / 100) * 0.16;
        const radius = r * r;

        if (!this.seeded) {
            this.seeded = true;
            for (let i = 0; i < SEEDS.length; i++) {
                const s = SEEDS[i];
                this.doSplat(s[0], s[1], s[2], s[3], pick(i / SEEDS.length), radius, 1.1);
            }
        }

        const p = this.pointer;
        if (p.moved && (Math.abs(p.dx) > 0.01 || Math.abs(p.dy) > 0.01)) {
            const gain = (this.force / 100) * 0.9 * (1 + p.down);
            this.doSplat(
                p.x,
                p.y,
                p.dx * gain,
                p.dy * gain,
                pick(this.colorPhase + p.x),
                radius,
                dtReal * INJECT_RATE
            );
        }
        p.dx = 0;
        p.dy = 0;

        if (this.drift > 0) {
            const nx = 0.5 + 0.32 * Math.sin(this.clock * 0.55) * Math.cos(this.clock * 0.17);
            const ny = 0.5 + 0.28 * Math.sin(this.clock * 0.43 + 1.7);
            const w = this.cssW || 1;
            const h = this.cssH || 1;
            const fx = (nx - this.ax) * w * (this.drift / 100) * 1.6;
            const fy = (ny - this.ay) * h * (this.drift / 100) * 1.6;
            this.ax = nx;
            this.ay = ny;
            if (Math.abs(fx) > 0.01 || Math.abs(fy) > 0.01) {
                this.doSplat(
                    nx,
                    ny,
                    fx,
                    fy,
                    pick(this.colorPhase),
                    radius * 0.8,
                    dtReal * INJECT_RATE * (this.drift / 100)
                );
            }
        }

        const setTexel = (pass, t) => gl.uniform2f(pass.u.uTexel, t.texelX, t.texelY);

        gl.useProgram(this.curl.prog);
        setTexel(this.curl, this.vel.read);
        gl.uniform1i(this.curl.u.uVel, this.bindTex(this.vel.read.tex, 0));
        this.blit(this.crl);

        gl.useProgram(this.vorticity.prog);
        setTexel(this.vorticity, this.vel.read);
        gl.uniform1i(this.vorticity.u.uVel, this.bindTex(this.vel.read.tex, 0));
        gl.uniform1i(this.vorticity.u.uCurl, this.bindTex(this.crl.tex, 1));
        gl.uniform1f(this.vorticity.u.uCurlAmt, (this.swirl / 50) * CURL_AT_50);
        gl.uniform1f(this.vorticity.u.uDt, dt);
        this.blit(this.vel.write);
        this.vel.swap();

        gl.useProgram(this.divergence.prog);
        setTexel(this.divergence, this.vel.read);
        gl.uniform1i(this.divergence.u.uVel, this.bindTex(this.vel.read.tex, 0));
        this.blit(this.div);

        gl.useProgram(this.clearPass.prog);
        setTexel(this.clearPass, this.prs.read);
        gl.uniform1i(this.clearPass.u.uTex, this.bindTex(this.prs.read.tex, 0));
        gl.uniform1f(this.clearPass.u.uValue, PRESSURE_DECAY);
        this.blit(this.prs.write);
        this.prs.swap();

        gl.useProgram(this.pressure.prog);
        setTexel(this.pressure, this.prs.read);
        gl.uniform1i(this.pressure.u.uDivergence, this.bindTex(this.div.tex, 0));
        for (let i = 0; i < PRESSURE_ITERATIONS; i++) {
            gl.uniform1i(this.pressure.u.uPressure, this.bindTex(this.prs.read.tex, 1));
            this.blit(this.prs.write);
            this.prs.swap();
        }

        gl.useProgram(this.gradient.prog);
        setTexel(this.gradient, this.vel.read);
        gl.uniform1i(this.gradient.u.uPressure, this.bindTex(this.prs.read.tex, 0));
        gl.uniform1i(this.gradient.u.uVel, this.bindTex(this.vel.read.tex, 1));
        this.blit(this.vel.write);
        this.vel.swap();

        gl.useProgram(this.advect.prog);
        setTexel(this.advect, this.vel.read);
        gl.uniform2f(this.advect.u.uTexelSrc, this.vel.read.texelX, this.vel.read.texelY);
        gl.uniform1f(this.advect.u.uDt, dt);
        gl.uniform1f(this.advect.u.uDiss, VELOCITY_DISSIPATION);
        gl.uniform1i(this.advect.u.uVel, this.bindTex(this.vel.read.tex, 0));
        gl.uniform1i(this.advect.u.uSrc, this.bindTex(this.vel.read.tex, 0));
        this.blit(this.vel.write);
        this.vel.swap();

        gl.uniform2f(this.advect.u.uTexel, this.vel.read.texelX, this.vel.read.texelY);
        gl.uniform2f(this.advect.u.uTexelSrc, this.dye.read.texelX, this.dye.read.texelY);
        gl.uniform1f(this.advect.u.uDiss, (Math.max(1, this.dissipation) / 100) * 2.2);
        gl.uniform1i(this.advect.u.uVel, this.bindTex(this.vel.read.tex, 0));
        gl.uniform1i(this.advect.u.uSrc, this.bindTex(this.dye.read.tex, 1));
        this.blit(this.dye.write);
        this.dye.swap();

        gl.useProgram(this.display.prog);
        gl.uniform2f(this.display.u.uTexel, this.dye.read.texelX, this.dye.read.texelY);
        gl.uniform1i(this.display.u.uTex, this.bindTex(this.dye.read.tex, 0));
        gl.uniform1f(this.display.u.uGain, 1.0);
        gl.bindFramebuffer(gl.FRAMEBUFFER, null);
        gl.viewport(0, 0, this.canvas.width, this.canvas.height);
        gl.clearColor(0, 0, 0, 0);
        gl.clear(gl.COLOR_BUFFER_BIT);
        gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    }
}
