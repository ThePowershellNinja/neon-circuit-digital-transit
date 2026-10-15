#version 140
#include "colormanagement.glsl"

uniform sampler2D sampler;
uniform int textureWidth;
uniform int textureHeight;
uniform float uProgress;
uniform float uSeed;
uniform float uViewX;
uniform float uViewY;
uniform float uViewWidth;
uniform float uViewHeight;
uniform float uOriginX;
uniform float uOriginY;
uniform float uWindowWidth;
uniform float uWindowHeight;
uniform float uPaddingX;
uniform float uPaddingY;
uniform float uTargetX;
uniform float uTargetY;
uniform float uTargetSize;

in vec2 texcoord0;
out vec4 fragColor;

const float peelStart = 0.02;
const float peelSpan = 0.58;
const float peelRipple = 0.018;
const float peelJitter = 0.008;
const float peelMaxDelay = 0.62;

uint scramble(uint value)
{
    value ^= value >> 16u;
    value *= 0x7feb352du;
    value ^= value >> 15u;
    value *= 0x846ca68bu;
    return value ^ (value >> 16u);
}

vec4 randomFor(float index)
{
    uint key = uint(index) ^ (uint(uSeed) * 0x9e3779b9u);
    return vec4(scramble(key), scramble(key + 0x68e31da4u),
                scramble(key + 0xb5297a4du), scramble(key + 0x1b56c4e9u)) / 4294967296.0;
}

float rowBoundary(int row, int rows)
{
    if (row <= 0) return 0.0;
    if (row >= rows) return 1.0;
    return (float(row) + (randomFor(1024.0 + float(row)).x - 0.5) * 0.84) / float(rows);
}

float columnBoundary(int column, int row, int columns)
{
    if (column <= 0) return 0.0;
    if (column >= columns) return 1.0;
    return (float(column) + (randomFor(2048.0 + float(row) * 31.0 + float(column)).y - 0.5) * 0.84)
        / float(columns);
}

vec2 peelWeights()
{
    vec2 size = vec2(uWindowWidth, uWindowHeight);
    vec2 flow = (vec2(uTargetX, uTargetY) - vec2(uOriginX, uOriginY) - size * 0.5) * size;
    return flow / max(abs(flow.x) + abs(flow.y), 1.0);
}

float departureDelay(vec2 sourceUV, vec2 weights, float jitter, float seedPhase)
{
    float front = 0.5 - dot(sourceUV - 0.5, weights);
    float tangent = dot(sourceUV - 0.5, vec2(-weights.y, weights.x));
    float ripple = sin(tangent * 11.0 + seedPhase * 6.2831853) * peelRipple;
    return clamp(peelStart + front * peelSpan + ripple + (jitter - 0.5) * peelJitter,
                 0.0, peelMaxDelay);
}

vec2 phaseBounds(float p, float delayLow, float delayHigh)
{
    vec2 progress = clamp((vec2(p) - vec2(delayHigh, delayLow))
        / (1.0 - vec2(delayHigh, delayLow)), 0.0, 1.0);
    vec2 eased = progress * progress * (3.0 - 2.0 * progress);
    vec2 first = mix(progress, eased, 0.4);
    vec2 last = mix(progress, eased, 0.9);
    return vec2(min(first.x, last.x), max(first.y, last.y));
}

vec2 bezierBounds(vec2 start, vec2 control, vec2 end, vec2 t)
{
    vec3 first = vec3((1.0 - t.x) * (1.0 - t.x), 2.0 * (1.0 - t.x) * t.x, t.x * t.x);
    vec3 middle = vec3((1.0 - t.x) * (1.0 - t.y), t.x + t.y - 2.0 * t.x * t.y, t.x * t.y);
    vec3 last = vec3((1.0 - t.y) * (1.0 - t.y), 2.0 * (1.0 - t.y) * t.y, t.y * t.y);
    vec3 low = vec3(start.x, control.x, end.x);
    vec3 high = vec3(start.y, control.y, end.y);
    return vec2(min(min(dot(first, low), dot(middle, low)), dot(last, low)),
                max(max(dot(first, high), dot(middle, high)), dot(last, high)));
}

bool flightContainsX(float p, float pixelX, int columns, int rows, float curl)
{
    vec2 start = vec2(uOriginX, uOriginX + uWindowWidth);
    vec2 end = vec2(uTargetX) + vec2(-0.5, 0.5) * min(uTargetSize * 0.6, 24.0);
    vec2 control = vec2(min(mix(end.x, start.x, 0.06), mix(end.x, start.x, 0.3)),
                        max(mix(end.y, start.y, 0.06), mix(end.y, start.y, 0.3)));
    control += vec2(min(curl * 0.45, curl * 1.15), max(curl * 0.45, curl * 1.15));
    control += vec2(-0.5, 0.5) * min(uWindowWidth * 0.22, 120.0);
    vec2 bounds = bezierBounds(start, control, end, phaseBounds(p, 0.0, peelMaxDelay));
    float margin = 0.7 * 1.84 * uWindowWidth / float(columns)
        + 0.06 * 1.84 * uWindowHeight / float(rows) + 2.0;
    return pixelX >= bounds.x - margin && pixelX <= bounds.y + margin;
}

uint visibleRowsFor(float p, float pixelY, int columns, int rows)
{
    uint visible = 0u;
    vec2 weights = peelWeights();
    vec2 end = vec2(uTargetY) + vec2(-0.5, 0.5) * min(uTargetSize * 0.6, 24.0);
    for (int row = 0; row < 24; ++row) {
        if (row >= rows) break;
        float low = rowBoundary(row, rows) * uWindowHeight;
        float high = rowBoundary(row + 1, rows) * uWindowHeight;
        float sourceY = (low + high) * 0.5;
        float start = uOriginY + sourceY;
        float front = 0.5 - (sourceY / uWindowHeight - 0.5) * weights.y;
        float roughness = peelRipple + peelJitter * 0.5;
        vec2 delay = clamp(peelStart
            + (vec2(front) + vec2(-0.5, 0.5) * abs(weights.x)) * peelSpan
            + vec2(-roughness, roughness), 0.0, peelMaxDelay);
        vec2 phase = phaseBounds(p, delay.x, delay.y);
        vec2 control = vec2(min(mix(start, end.x, 0.15), mix(start, end.x, 0.5)),
                            max(mix(start, end.y, 0.15), mix(start, end.y, 0.5)))
            + vec2(-0.09, 0.09) * uWindowHeight;
        vec2 bounds = bezierBounds(vec2(start), control, end, phase);
        // Include the maximum stretch, rotation and torn contour, not just each piece's center.
        float margin = 0.625 * (high - low) + 0.105 * 1.84 * uWindowWidth / float(columns) + 2.0;
        if (pixelY >= bounds.x - margin && pixelY <= bounds.y + margin) visible |= 1u << uint(row);
    }
    return visible;
}

vec4 sampleWindow(vec2 point)
{
    vec2 uv = (point + vec2(uPaddingX, uPaddingY))
        / max(vec2(textureWidth, textureHeight), vec2(1.0));
    if (any(lessThan(uv, vec2(0.0))) || any(greaterThan(uv, vec2(1.0)))) return vec4(0.0);
    uv.y = 1.0 - uv.y;
    return texture(sampler, uv);
}

void main()
{
    float p = clamp(uProgress, 0.0, 1.0);
    // KWin's redirected texture is bottom-up; screen-space flight paths are top-down.
    vec2 pixel = vec2(texcoord0.x, 1.0 - texcoord0.y)
        * vec2(uViewWidth, uViewHeight) + vec2(uViewX, uViewY);
    vec2 origin = vec2(uOriginX, uOriginY);
    vec2 windowSize = vec2(uWindowWidth, uWindowHeight);
    vec4 result = vec4(0.0);

    if (p < 0.00001) {
        result = sampleWindow(pixel - origin);
    } else if (p < 0.99999) {
        int columns = int(clamp(floor(uWindowWidth / 32.0), 18.0, 30.0));
        int rows = int(clamp(floor(uWindowHeight / 16.0), 16.0, 24.0));
        vec2 target = vec2(uTargetX, uTargetY);
        vec2 weights = peelWeights();
        vec4 flight = randomFor(9000.0);
        float direction = flight.x < 0.5 ? -1.0 : 1.0;
        float curl = direction * (0.55 + flight.y * 0.45) * min(uWindowWidth * 0.18, 125.0);
        uint visibleRows = flightContainsX(p, pixel.x, columns, rows, curl)
            ? visibleRowsFor(p, pixel.y, columns, rows) : 0u;
        float globalInterference = smoothstep(0.0, 0.10, p) * (1.0 - smoothstep(0.90, 1.0, p));
        float beat = floor(p * 36.0);
        for (int group = 0; group < 24; ++group) {
            if (group >= rows || visibleRows == 0u) break;
            int row = (group * 73) % rows;
            if ((visibleRows & (1u << uint(row))) == 0u) continue;
            float rowLow = rowBoundary(row, rows) * uWindowHeight;
            float rowHigh = rowBoundary(row + 1, rows) * uWindowHeight;
            for (int item = 0; item < 30; ++item) {
                if (item >= columns) break;
                int column = (item * 73) % columns;
                int index = row * columns + column;
                vec2 low = vec2(columnBoundary(column, row, columns) * uWindowWidth, rowLow);
                vec2 high = vec2(columnBoundary(column + 1, row, columns) * uWindowWidth, rowHigh);
                vec2 cellSize = high - low;
                vec2 sourceCenter = (low + high) * 0.5;
                vec2 sourceUV = sourceCenter / windowSize;
                vec4 random = randomFor(float(index));
                float delay = departureDelay(sourceUV, weights, random.x, flight.z);
                if (p <= delay) {
                    // The wave has not reached this piece: keep it seamless and undistorted.
                    vec2 source = pixel - origin;
                    if (all(greaterThanEqual(source, low)) && all(lessThan(source, high))) {
                        vec4 piece = sampleWindow(source);
                        result = piece + result * (1.0 - piece.a);
                    }
                    continue;
                }
                float progress = clamp((p - delay) / (1.0 - delay), 0.0, 1.0);
                float eased = progress * progress * (3.0 - 2.0 * progress);
                float t = mix(progress, eased, 0.4 + random.w * 0.5);
                float joining = smoothstep(0.0, 0.06, t);
                float interference = globalInterference * joining;
                float wave = 4.0 * t * (1.0 - t);
                vec2 start = origin + sourceCenter;
                vec2 end = target + (random.yz - 0.5) * min(uTargetSize * 0.6, 24.0);
                vec2 control = vec2(
                    mix(end.x, start.x, 0.06 + random.z * 0.24) + curl * (0.45 + random.y * 0.7)
                        + (random.w - 0.5) * min(uWindowWidth * 0.22, 120.0),
                    mix(start.y, end.y, 0.15 + random.w * 0.35) + (random.z - 0.5) * uWindowHeight * 0.18
                );
                vec2 center = (1.0 - t) * (1.0 - t) * start
                    + 2.0 * (1.0 - t) * t * control + t * t * end;
                float scale = mix(1.0, 0.94, joining) - 0.78 * smoothstep(0.28 + random.y * 0.28, 1.0, t);
                vec2 stretch = vec2(1.0 - wave * (0.05 + random.x * 0.27),
                                    1.0 + wave * (0.05 + random.z * 0.20)) * scale;
                vec2 delta = (pixel - center) / max(stretch, vec2(0.01));
                float angle = (random.w - 0.5) * 0.24 * wave;
                float cosine = 1.0 - angle * angle * 0.5;
                vec2 local = vec2(cosine * delta.x + angle * delta.y,
                                 -angle * delta.x + cosine * delta.y);
                if (abs(local.y) > cellSize.y * 0.5 || abs(local.x) > cellSize.x * 0.7) continue;
                float band = floor((local.y + cellSize.y * 0.5) / 3.0);
                vec4 distortion = randomFor(float(index) * 17.0 + band * 11.0 + beat * 7.0);
                float tear = smoothstep(0.52, 0.90, distortion.x) * interference;
                local.x -= (distortion.y - 0.5) * cellSize.x * 0.36 * tear;
                vec2 edge = cellSize * 0.5 - abs(local);
                if (min(edge.x, edge.y) < 0.0) continue;

                vec2 source = sourceCenter + local;
                float pixelStep = 1.0 + floor(wave * 2.0);
                vec2 sampled = mix(source, (floor(source / pixelStep) + 0.5) * pixelStep, wave);
                vec4 piece = sampleWindow(sampled);
                float edgeMask = mix(1.0, smoothstep(0.0, 1.0, min(edge.x, edge.y)), joining);
                float fade = 1.0 - smoothstep(0.90, 1.0, progress);
                if (interference > 0.0 && piece.a > 0.0) {
                    float separation = (1.0 + distortion.z * 3.5) * interference * (0.35 + tear * 0.65);
                    vec4 red = sampleWindow(sampled + vec2(separation, 0.0));
                    vec4 blue = sampleWindow(sampled - vec2(separation, 0.0));
                    vec3 split = min(vec3(red.r, piece.g, blue.b), vec3(piece.a));
                    piece.rgb = mix(piece.rgb, split, interference * 0.75);
                    float scanline = smoothstep(0.62, 0.95, fract((source.y + beat * 0.3) / 3.0));
                    piece.rgb *= 1.0 - scanline * interference * 0.30;
                    float dataBand = step(0.94, randomFor(floor(source.y / 9.0) + beat * 3.0).x) * interference;
                    piece.rgb = mix(piece.rgb, vec3(0.56, 0.93, 0.30) * piece.a, dataBand * 0.32);
                }
                piece *= edgeMask * fade;
                result = piece + result * (1.0 - piece.a);
            }
        }
    }

    fragColor = sourceEncodingToNitsInDestinationColorspace(result);
    fragColor = nitsToDestinationEncoding(fragColor);
}
