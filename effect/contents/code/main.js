"use strict";

var shader = effect.addFragmentShader(Effect.MapTexture, "digital.frag");
var states = new Map();
var hooked = new Set();
var seeds = new Map();

function clear(window) {
    var state = states.get(window);
    if (!state) return;
    states.delete(window);
    if (state.animation) cancel(state.animation);
    if (state.progress) cancel(state.progress);
    if (state.uniforms) cancel(state.uniforms);
    if (state.retry) cancel(state.retry);
    window.setData(Effect.WindowForceBlurRole, null);
}

function canvasFor(rect, target) {
    var screen = effects.virtualScreenGeometry;
    var horizontalMargin = Math.min(rect.width * 0.22, 160) + 24;
    var left = Math.max(screen.x, Math.min(rect.x, target.x) - horizontalMargin);
    var top = Math.max(screen.y, Math.min(rect.y, target.y) - 48);
    var right = Math.min(screen.x + screen.width, Math.max(rect.x + rect.width, target.x + target.width) + horizontalMargin);
    var bottom = Math.min(screen.y + screen.height, Math.max(rect.y + rect.height, target.y + target.height) + 48);
    return {x: left, y: top, width: right - left, height: bottom - top};
}

function uniformsFor(window, canvas, target, seed) {
    var rect = window.geometry;
    var expanded = window.expandedGeometry;
    return {
        uViewX: (expanded.x - rect.x) * canvas.width / rect.width,
        uViewY: (expanded.y - rect.y) * canvas.height / rect.height,
        uViewWidth: expanded.width * canvas.width / rect.width,
        uViewHeight: expanded.height * canvas.height / rect.height,
        uOriginX: rect.x - canvas.x,
        uOriginY: rect.y - canvas.y,
        uWindowWidth: rect.width,
        uWindowHeight: rect.height,
        uPaddingX: rect.x - expanded.x,
        uPaddingY: rect.y - expanded.y,
        uTargetX: target.x + target.width / 2 - canvas.x,
        uTargetY: target.y + target.height / 2 - canvas.y,
        uTargetSize: Math.min(target.width, target.height),
        uSeed: seed === undefined ? 0 : seed
    };
}

function assignUniform(id, value, duration) {
    // Set the new value immediately without destroying the captured texture,
    // then keep publishing it per window for the lifetime of the flight.
    retarget(id, value, 1);
    freezeInTime(id, 1);
    retarget(id, value, duration);
    freezeInTime(id, -1);
}

function targetReady(window, state, target) {
    if (states.get(window) !== state || window.minimized !== state.minimized) return;
    var rect = window.geometry;
    var duration = animationTime(effect.readConfig("Duration", 300));
    if (duration <= 0) {
        finishWithoutTarget(window, state);
        return;
    }
    var canvas = canvasFor(rect, target);
    var values = uniformsFor(window, canvas, target, state.seed);
    var names = Object.keys(state.initial);
    for (var i = 0; i < names.length; i++) assignUniform(state.uniforms[i], values[names[i]], duration);
    var offset = {value1: canvas.x + canvas.width / 2 - rect.x - rect.width / 2,
        value2: canvas.y + canvas.height / 2 - rect.y - rect.height / 2};
    var size = {value1: canvas.width, value2: canvas.height};
    state.waiting = false;
    state.target = target;
    retarget(state.progress, state.minimized ? 1 : 0, duration);
    if (effect.readConfig("Diagnostics", false)) {
        console.info("NEON_DIGITAL_TARGET " + JSON.stringify({
            caption: window.caption, minimized: state.minimized, duration: duration, seed: state.seed, target: target, canvas: canvas,
            window: {x: rect.x, y: rect.y, width: rect.width, height: rect.height}
        }));
    }
    state.animation = animate({
        window: window,
        duration: duration,
        curve: QEasingCurve.Linear,
        keepAlive: false,
        animations: [
            {type: Effect.Size, from: size, to: size},
            {type: Effect.Translation, from: offset, to: offset},
            {type: Effect.Opacity, from: 1, to: 1}
        ]
    });
}

function finishWithoutTarget(window, state) {
    states.delete(window);
    var names = Object.keys(state.initial);
    for (var i = 0; i < names.length; i++) retarget(state.uniforms[i], state.initial[names[i]], 1);
    retarget(state.progress, state.minimized ? 1 : 0, 1);
    window.setData(Effect.WindowForceBlurRole, null);
}

function usableTarget(target) {
    if (!target || !["x", "y", "width", "height"].every(function (key) {
        return typeof target[key] === "number" && isFinite(target[key]);
    }) || target.width <= 0 || target.height <= 0) return false;
    var desktop = effects.virtualScreenGeometry;
    var x = target.x + target.width / 2;
    var y = target.y + target.height / 2;
    return target.width <= desktop.width && target.height <= desktop.height
        && x >= desktop.x && x < desktop.x + desktop.width
        && y >= desktop.y && y < desktop.y + desktop.height;
}

function queryTarget(window, state) {
    if (states.get(window) !== state || !state.waiting) return;
    var target = window.iconGeometry;
    if (state.attempts > 0 && usableTarget(target)) {
        targetReady(window, state, target);
    } else if (++state.attempts < 25) {
        state.retry = animate({
            window: window, duration: 16, keepAlive: false, type: Effect.Opacity,
            from: state.minimized ? 1 : 0, to: state.minimized ? 1 : 0
        });
    } else {
        console.warn("Neon Digital Transit: no usable native task icon target for " + window.caption);
        finishWithoutTarget(window, state);
    }
}

function transition(window) {
    if (window.minimized && !states.has(window)) seeds.set(window, Math.floor(Math.random() * 65536));
    clear(window);
    if (effects.hasActiveFullScreenEffect || !(window.normalWindow || window.dialog)) return;
    var state = {minimized: window.minimized, waiting: true, attempts: 0, seed: seeds.get(window)};
    states.set(window, state);
    window.setData(Effect.WindowForceBlurRole, true);
    // Capture the window before waiting for the taskbar layout. Starting a
    // shader snapshot from an animation-ended callback can capture an empty frame.
    state.initial = uniformsFor(window, window.geometry, window.geometry, state.seed);
    state.uniforms = animate({
        window: window, duration: 60000, keepAlive: false,
        animations: Object.keys(state.initial).map(function (name) {
            return {type: Effect.ShaderUniform, fragmentShader: shader, uniform: name,
                from: state.initial[name], to: state.initial[name], curve: QEasingCurve.Linear};
        })
    });
    state.progress = animate({
        window: window, duration: 60000, keepAlive: false,
        animations: [{
            type: Effect.ShaderUniform, fragmentShader: shader, uniform: "uProgress",
            from: state.minimized ? 0 : 1, to: state.minimized ? 0 : 1,
            curve: QEasingCurve.Linear
        }]
    });
    queryTarget(window, state);
}

function hook(window) {
    if (hooked.has(window)) return;
    hooked.add(window);
    seeds.set(window, Math.floor(Math.random() * 65536));
    window.minimizedChanged.connect(function () { transition(window); });
}

effect.animationEnded.connect(function (window) {
    var state = states.get(window);
    if (!state) return;
    if (state.waiting && state.retry) {
        state.retry = null;
        queryTarget(window, state);
    } else if (!state.waiting && state.animation) {
        if (effect.readConfig("Diagnostics", false)) {
            console.info("NEON_DIGITAL_FINISH " + JSON.stringify({
                caption: window.caption, minimized: state.minimized,
                target: state.target, icon: window.iconGeometry
            }));
        }
        states.delete(window);
        window.setData(Effect.WindowForceBlurRole, null);
    }
});
effects.windowAdded.connect(hook);
effects.windowDeleted.connect(function (window) {
    clear(window);
    seeds.delete(window);
    hooked.delete(window);
});
effects.stackingOrder.forEach(hook);
