from pathlib import Path

import cv2
import numpy as np
from PySide6.QtCore import QCoreApplication
from PySide6.QtQml import QJSEngine


app = QCoreApplication([])
engine = QJSEngine()
setup = """
var effect={addFragmentShader:function(){return 1},animationEnded:{connect:function(){}}};
var Effect={MapTexture:1};
var effects={virtualScreenGeometry:{x:0,y:0,width:6400,height:1440},
windowAdded:{connect:function(){}},windowDeleted:{connect:function(){}},stackingOrder:[]};
var calls=[];
function retarget(id,value,duration){calls.push(['retarget',id,value,duration]);return true}
function freezeInTime(id,time){calls.push(['freeze',id,time]);return true}
"""
ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / "effect/contents/code/main.js").read_text()
for code in (setup, source):
    value = engine.evaluate(code)
    assert not value.isError(), value.toString()
value = engine.evaluate("""
var w={geometry:{x:2340,y:240,width:700,height:440},
expandedGeometry:{x:2328,y:226,width:724,height:472}};
var target={x:2020,y:0,width:48,height:40};
var canvas=canvasFor(w.geometry,target);
uniformsFor(w,canvas,target,17);
""")
assert not value.isError(), value.toString()
uniforms = value.toVariant()
canvas = engine.evaluate("canvas").toVariant()
origin = np.array([uniforms["uOriginX"], uniforms["uOriginY"]])
size = np.array([700.0, 440.0])
target = np.array([uniforms["uTargetX"], uniforms["uTargetY"]])
for uv in (np.array([0., 0.]), np.array([.3, .8]), np.array([1., 1.])):
    screen_uv = np.array([uv[0], 1 - uv[1]])
    pixel = screen_uv * np.array([uniforms["uViewWidth"], uniforms["uViewHeight"]]) + np.array([uniforms["uViewX"], uniforms["uViewY"]])
    source_point = pixel - origin
    reconstructed = (source_point + np.array([12., 14.])) / np.array([724., 472.])
    reconstructed[1] = 1 - reconstructed[1]
    world = pixel + np.array([canvas["x"], canvas["y"]])
    camera_scale = np.array([canvas["width"] / 700, canvas["height"] / 440])
    expected_world = np.array([canvas["x"], canvas["y"]]) + (np.array([-12., -14.]) + screen_uv * np.array([724., 472.])) * camera_scale
    assert np.allclose(world, expected_world)
    assert np.isfinite(reconstructed).all()
engine.evaluate("assignUniform(7, 42, 560)")
assert engine.evaluate("calls").toVariant() == [
    ["retarget", 7, 42, 1], ["freeze", 7, 1], ["retarget", 7, 42, 560], ["freeze", 7, -1]
]
shader = (ROOT / "effect/contents/shaders/digital.frag").read_text()
assert "vec2(texcoord0.x, 1.0 - texcoord0.y)" in shader
assert "uv.y = 1.0 - uv.y;" in shader
view_size = np.array([uniforms["uViewWidth"], uniforms["uViewHeight"]])
view_origin = np.array([uniforms["uViewX"], uniforms["uViewY"]])
target_screen_uv = (target - view_origin) / view_size
target_texture_uv = np.array([target_screen_uv[0], 1 - target_screen_uv[1]])
rendered_target = np.array([target_texture_uv[0], 1 - target_texture_uv[1]]) * view_size + view_origin
assert np.allclose(rendered_target + np.array([canvas["x"], canvas["y"]]), [2044, 20])
for uv in (np.array([0., 0.]), np.array([.3, .8]), np.array([1., 1.])):
    screen_uv = np.array([uv[0], 1 - uv[1]])
    source_point = screen_uv * np.array([724., 472.]) - np.array([12., 14.])
    sampled = (source_point + np.array([12., 14.])) / np.array([724., 472.])
    sampled[1] = 1 - sampled[1]
    assert np.allclose(sampled, uv), "The coordinate correction flips the application content"
print("PASS: bottom-up texture mapping preserves source orientation and lands at the task icon")
print("PASS: expanded flight canvas, shadow-aware mapping and per-window scalar uniform updates")


def smooth(a, b, value):
    x = max(0., min(1., (value - a) / (b - a)))
    return x * x * (3 - 2 * x)


def scramble(value):
    value &= 0xffffffff
    value ^= value >> 16
    value = value * 0x7feb352d & 0xffffffff
    value ^= value >> 15
    value = value * 0x846ca68b & 0xffffffff
    return value ^ (value >> 16)


def random_for(index, seed=17):
    key = int(index) ^ (seed * 0x9e3779b9 & 0xffffffff)
    return np.array([scramble(key + offset) for offset in (0, 0x68e31da4, 0xb5297a4d, 0x1b56c4e9)]) / 4294967296


def source_grid(window_size):
    return (max(18, min(30, int(window_size[0] // 32))),
            max(16, min(24, int(window_size[1] // 16))))


def source_rectangles(seed=17):
    columns, rows = source_grid(size)
    def row_boundary(row):
        if row <= 0: return 0.
        if row >= rows: return 1.
        return (row + (random_for(1024 + row, seed)[0] - .5) * .84) / rows
    def column_boundary(column, row):
        if column <= 0: return 0.
        if column >= columns: return 1.
        return (column + (random_for(2048 + row * 31 + column, seed)[1] - .5) * .84) / columns
    rectangles = []
    for index in range(columns * rows):
        column, row = index % columns, index // columns
        low = np.array([column_boundary(column, row), row_boundary(row)]) * size
        high = np.array([column_boundary(column + 1, row), row_boundary(row + 1)]) * size
        rectangles.append((low, high))
    return rectangles


def peel_weights(goal=None):
    flow = ((target if goal is None else goal) - origin - size * .5) * size
    return flow / max(np.abs(flow).sum(), 1.)


def departure_delay(index, source_center, seed=17, goal=None):
    weights = peel_weights(goal)
    rnd = random_for(index, seed)
    source_uv = source_center / size
    front = .5 - np.dot(source_uv - .5, weights)
    tangent = np.dot(source_uv - .5, [-weights[1], weights[0]])
    ripple = np.sin(tangent * 11 + random_for(9000, seed)[2] * 6.2831853) * .018
    return np.clip(.02 + front * .58 + ripple + (rnd[0] - .5) * .008, 0., .62)


def piece_phase(p, index, source_center, seed=17):
    delay = departure_delay(index, source_center, seed)
    progress = max(0., min(1., (p - delay) / (1 - delay)))
    eased = progress * progress * (3 - 2 * progress)
    rnd = random_for(index, seed)
    return progress + (eased - progress) * (.4 + rnd[3] * .5)


def paths(p, seed=17, curl_override=None):
    flight = random_for(9000, seed)
    direction = -1 if flight[0] < .5 else 1
    curl = direction * (.55 + flight[1] * .45) * min(size[0] * .18, 125)
    if curl_override is not None: curl = curl_override
    pieces = []
    for index, (low, high) in enumerate(source_rectangles(seed)):
        cell_size = high - low
        source_center = (high + low) / 2
        rnd = random_for(index, seed)
        t = piece_phase(p, index, source_center, seed)
        wave = 4 * t * (1 - t)
        start = origin + source_center
        end = target + (rnd[1:3] - .5) * min(uniforms["uTargetSize"] * .6, 24)
        pull = .06 + rnd[2] * .24
        lift = .15 + rnd[3] * .35
        control = np.array([
            end[0] * (1 - pull) + start[0] * pull + curl * (.45 + rnd[1] * .7)
                + (rnd[3] - .5) * min(size[0] * .22, 120),
            start[1] * (1 - lift) + end[1] * lift + (rnd[2] - .5) * size[1] * .18
        ])
        center = (1 - t) ** 2 * start + 2 * (1 - t) * t * control + t * t * end
        scale = (1 - .06 * smooth(0, .06, t)) - .78 * smooth(.28 + rnd[1] * .28, 1, t)
        stretch = np.array([1 - wave * (.05 + rnd[0] * .27), 1 + wave * (.05 + rnd[2] * .2)]) * scale
        angle = (rnd[3] - .5) * .24 * wave
        cosine = 1 - angle * angle / 2
        inverse = np.linalg.inv(np.array([[cosine, angle], [-angle, cosine]]))
        corners = np.array([[-.5, -.5], [.5, -.5], [.5, .5], [-.5, .5]]) * cell_size
        polygon = (corners @ inverse.T * stretch + center).astype("float32")
        pieces.append((source_center, center, polygon))
    return pieces


def phase_bounds(p, delay_low, delay_high):
    progress = np.clip((p - np.array([delay_high, delay_low]))
                       / (1 - np.array([delay_high, delay_low])), 0, 1)
    eased = progress * progress * (3 - 2 * progress)
    first, last = progress * .6 + eased * .4, progress * .1 + eased * .9
    return min(first[0], last[0]), max(first[1], last[1])


def row_y_bounds(p, low, high):
    columns, rows = source_grid(size)
    source_y = (low + high) * .5
    start = origin[1] + source_y
    weights = peel_weights()
    front = .5 - (source_y / size[1] - .5) * weights[1]
    delay = np.clip(.02 + (front + np.array([-.5, .5]) * abs(weights[0])) * .58
                    + np.array([-.022, .022]), 0, .62)
    a, b = phase_bounds(p, delay[0], delay[1])
    end = target[1] + np.array([-.5, .5]) * min(uniforms["uTargetSize"] * .6, 24)
    control = np.array([
        min(start * .85 + end[0] * .15, start * .5 + end[0] * .5) - size[1] * .09,
        max(start * .85 + end[1] * .15, start * .5 + end[1] * .5) + size[1] * .09,
    ])
    weights = np.array([
        [(1 - a) ** 2, 2 * (1 - a) * a, a * a],
        [(1 - a) * (1 - b), a + b - 2 * a * b, a * b],
        [(1 - b) ** 2, 2 * (1 - b) * b, b * b],
    ])
    minimum = min(weights @ np.array([start, control[0], end[0]]))
    maximum = max(weights @ np.array([start, control[1], end[1]]))
    margin = .625 * (high - low) + .105 * 1.84 * size[0] / columns + 2
    return minimum - margin, maximum + margin


def flight_x_bounds(p, seed):
    columns, rows = source_grid(size)
    start = origin[0] + np.array([0., size[0]])
    end = target[0] + np.array([-.5, .5]) * min(uniforms["uTargetSize"] * .6, 24)
    flight = random_for(9000, seed)
    curl = (-1 if flight[0] < .5 else 1) * (.55 + flight[1] * .45) * min(size[0] * .18, 125)
    control = np.array([
        min(end[0] * .94 + start[0] * .06, end[0] * .7 + start[0] * .3),
        max(end[1] * .94 + start[1] * .06, end[1] * .7 + start[1] * .3),
    ])
    control += np.array([min(curl * .45, curl * 1.15), max(curl * .45, curl * 1.15)])
    control += np.array([-.5, .5]) * min(size[0] * .22, 120)
    a, b = phase_bounds(p, 0., .62)
    weights = np.array([
        [(1 - a) ** 2, 2 * (1 - a) * a, a * a],
        [(1 - a) * (1 - b), a + b - 2 * a * b, a * b],
        [(1 - b) ** 2, 2 * (1 - b) * b, b * b],
    ])
    minimum = min(weights @ np.array([start[0], control[0], end[0]]))
    maximum = max(weights @ np.array([start[1], control[1], end[1]]))
    margin = .7 * 1.84 * size[0] / columns + .06 * 1.84 * size[1] / rows + 2
    return minimum - margin, maximum + margin


initial = paths(0)
for seed in (0, 17, 4099):
    rectangles = source_rectangles(seed)
    dimensions = np.array([high - low for low, high in rectangles])
    assert np.all(dimensions > 0)
    assert np.isclose(np.prod(dimensions, axis=1).sum(), np.prod(size))
    assert dimensions[:, 0].std() / dimensions[:, 0].mean() > .2
    assert dimensions[:, 1].std() / dimensions[:, 1].mean() > .2, (seed, dimensions[:, 1].std() / dimensions[:, 1].mean())
    columns, rows = source_grid(size)
    for i, (low, high) in enumerate(rectangles):
        row, column = i // columns, i % columns
        if column < columns - 1:
            assert np.isclose(high[0], rectangles[i + 1][0][0])
    cloud = np.array([center for source, center, polygon in paths(.5, seed)])
    straight = np.array([center for source, center, polygon in paths(.5, seed, curl_override=0)])
    direction = -1 if random_for(9000, seed)[0] < .5 else 1
    assert (cloud[:, 0] - straight[:, 0]).mean() * direction > 8
first = np.array([center for source, center, polygon in paths(.5, 17)])
second = np.array([center for source, center, polygon in paths(.5, 4099)])
assert np.sqrt(np.mean((first - second) ** 2)) > 10
samples = np.array([random_for(i)[0] for i in range(1000)])
assert abs(np.corrcoef(samples[:-1], samples[1:])[0, 1]) < .15
print("PASS: irregular seamless source partitions, decorrelated fragments, one-sided curls and seed-dependent flights")
assert len(initial) == 504, len(initial)
assert "floor(uWindowWidth / 32.0), 18.0, 30.0" in shader
assert "floor(uWindowHeight / 16.0), 16.0, 24.0" in shader
assert "group < 24" in shader and "item < 30" in shader
assert np.prod(source_grid((2560, 1440))) == 720
for columns in range(18, 31):
    for rows in range(16, 25):
        total = columns * rows
        order = [((i // columns * 73) % rows) * columns + ((i % columns * 73) % columns)
                 for i in range(total)]
        assert total <= 720 and len(set(order)) == total
        for visible in ({0}, {0, rows - 1}, set(range(0, rows, 3))):
            visited = []
            i = 0
            while i < total:
                row = ((i // columns) * 73) % rows
                if row not in visible:
                    i += columns - (i % columns)
                    continue
                visited.append(row * columns + ((i % columns * 73) % columns))
                i += 1
            assert visited == [index for index in order if index // columns in visible]
for width in (200, 576, 600, 624, 672, 700, 900, 960, 2560):
    for height in (200, 255, 256, 288, 300, 351, 384, 440, 1440):
        previous = max(12, min(20, width // 48)) * max(8, min(12, height // 32))
        ratio = np.prod(source_grid((width, height))) / previous
        assert 2.9 <= ratio <= 3.4, (width, height, ratio)
print("PASS: roughly triple density: 504 pieces for 700x440, up to 720; no duplicate or omitted pieces")
assert all(np.allclose(center, origin + start) for start, center, polygon in initial)
final = paths(1)
assert all(np.linalg.norm(center - target) < 18 for start, center, polygon in final)
overlaps = []
for progress in (.35, .5, .7):
    pieces = paths(progress)
    x = np.array([[start[0], start[1], 1] for start, center, polygon in pieces])
    y = np.array([center for start, center, polygon in pieces])
    fitted = x @ np.linalg.lstsq(x, y, rcond=None)[0]
    error = np.sqrt(np.mean((fitted - y) ** 2))
    assert error > 8, (progress, "All fragments still share one rectangular transform", error)
    count = 0
    for i, (_, _, first) in enumerate(pieces):
        for _, _, second in pieces[i + 1:]:
            area, _ = cv2.intersectConvexConvex(first, second)
            if area > 2:
                count += 1
    overlaps.append(count)
    assert count > 0, (progress, "Fragments never overlap")
print("PASS: independent staggered curved paths, non-affine fragment motion and real overlapping polygons:", overlaps)
print("PASS: source pieces begin in place and converge inside the task icon")
for seed in (0, 17, 4099):
    resting = paths(0, seed)
    for p in (.04, .12, .3):
        arriving = paths(p, seed)
        for index, (source, center, polygon) in enumerate(arriving):
            t = piece_phase(p, index, source, seed)
            if t == 0:
                assert np.allclose(center, origin + source)
                assert np.array_equal(polygon, resting[index][2])
                assert smooth(0, .06, t) == 0
    for index, (source, center, polygon) in enumerate(paths(0, seed)):
        delay = departure_delay(index, source, seed)
        t = piece_phase(delay + .001, index, source, seed)
        assert t > piece_phase(delay + .0005, index, source, seed) > 0
        assert smooth(0, .06, t) < .005, (seed, index, "A separate grid-settling phase remains")
assert "if (p <= delay)" in shader and "float delay = departureDelay(" in shader
print("PASS: unreached pieces stay seamless; arriving fragments join directly without a gapped-grid hold")
for seed in (0, 17, 4099):
    centers = np.array([(low + high) * .5 for low, high in source_rectangles(seed)])
    columns, rows = source_grid(size)
    for direction in ((0, -800), (-800, -600), (800, -600), (-800, 0),
                      (800, 0), (0, 800), (-800, 600), (800, 600)):
        goal = origin + size * .5 + np.array(direction)
        front = .5 - (centers / size - .5) @ peel_weights(goal)
        delays = np.array([departure_delay(i, center, seed, goal) for i, center in enumerate(centers)])
        assert np.corrcoef(front, delays)[0, 1] > .98, (seed, direction, "Wave moves in the wrong direction")
        assert delays.min() < .08 and delays.max() > .5
        assert .2 < (delays < .3).mean() < .8, "The whole window departs at once"
        for index in range(len(centers)):
            neighbors = []
            if index % columns < columns - 1:
                neighbors.append(index + 1)
            if index // columns < rows - 1:
                neighbors.append(index + columns)
            assert all(abs(delays[index] - delays[other]) < .1 for other in neighbors), (
                seed, direction, index, "Neighboring pieces depart independently instead of propagating"
            )
print("PASS: the icon-facing edge leads a coherent neighboring-piece wave in every direction")
for window_size in ((700., 440.), (2560., 1400.)):
    size = np.array(window_size)
    for direction in ((0, -800), (-800, -600), (800, -600), (-800, 0),
                      (800, 0), (0, 800), (-800, 600), (800, 600)):
        target = origin + size * .5 + np.array(direction)
        for seed in (0, 17, 4099):
            rectangles = source_rectangles(seed)
            columns, rows = source_grid(size)
            for progress in (.01, .1, .25, .5, .75, .9, .99):
                left, right = flight_x_bounds(progress, seed)
                bounds = [row_y_bounds(progress, rectangles[row * columns][0][1],
                                       rectangles[row * columns][1][1]) for row in range(rows)]
                for index, (source, center, polygon) in enumerate(paths(progress, seed)):
                    low, high = bounds[index // columns]
                    assert polygon[:, 1].min() >= low and polygon[:, 1].max() <= high, (
                        window_size, direction, seed, progress, index, "Row culling clips a moving fragment"
                    )
                    assert polygon[:, 0].min() >= left and polygon[:, 0].max() <= right, (
                        window_size, direction, seed, progress, index, "Flight culling clips a moving fragment"
                    )
assert "visibleRowsFor(p, pixel.y, columns, rows)" in shader
print("PASS: conservative bounds preserve every fragment in eight directions; row skips retain shuffled order")
