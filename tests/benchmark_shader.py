"""Optional real-GPU regression: optimized pixels must match unculled pixels."""

from pathlib import Path
import os
import re
import statistics
import struct
import sys
import traceback

import numpy as np
from PySide6.QtGui import QColor, QGuiApplication, QImage, QOffscreenSurface, QOpenGLContext, QSurfaceFormat
from PySide6.QtOpenGL import (
    QOpenGLBuffer, QOpenGLFramebufferObject, QOpenGLShader, QOpenGLShaderProgram,
    QOpenGLTexture, QOpenGLTimerQuery, QOpenGLVertexArrayObject,
)

# Keep both sides of a strict pixel comparison in the same instruction stream.
# This affects only this test process, not KWin or the distributed effect.
os.environ.setdefault("radeonsi_inline_uniforms", "false")


ROOT = Path(__file__).resolve().parents[1]
VERTEX = """#version 140
in vec2 position;
out vec2 texcoord0;
void main() {
    gl_Position = vec4(position, 0.0, 1.0);
    texcoord0 = (position + vec2(1.0)) * 0.5;
}
"""
COLOR_FUNCTIONS = """
vec4 sourceEncodingToNitsInDestinationColorspace(vec4 value) { return value; }
vec4 nitsToDestinationEncoding(vec4 value) { return value; }
"""
FIXTURES = [
    (700, 440, 1400, 900, 350, 200, x, y)
    for x, y in ((60, 20), (700, 20), (1340, 20), (60, 450), (1340, 450),
                 (60, 880), (700, 880), (1340, 880))
] + [(2560, 1400, 2928, 1440, 184, 0, 60, 20)]


def compile_program(fragment):
    program = QOpenGLShaderProgram()
    assert program.addShaderFromSourceCode(QOpenGLShader.Vertex, VERTEX), program.log()
    assert program.addShaderFromSourceCode(QOpenGLShader.Fragment, fragment), program.log()
    assert program.link() and program.bind(), program.log()
    program.enableAttributeArray("position")
    program.setAttributeBuffer("position", 0x1406, 0, 2, 8)
    return program


def configure(gl, program, values):
    assert program.bind()
    for name, value in values.items():
        location = program.uniformLocation(name)
        assert location >= 0, name
        if isinstance(value, int):
            gl.glUniform1i(location, value)
        else:
            gl.glUniform1f(location, value)


def difference(first, second):
    return np.abs(np.frombuffer(first.constBits(), dtype=np.uint8).astype(int)
                  - np.frombuffer(second.constBits(), dtype=np.uint8).astype(int))


def check_shader(gl, query, path):
    fragment = path.read_text().replace('#include "colormanagement.glsl"', COLOR_FUNCTIONS)
    comparison, count = re.subn(
        r"(uint visibleRows =.*?;)", r"\1\nif (uUnculled) visibleRows = 0x00ffffffu;",
        fragment, count=1, flags=re.DOTALL)
    comparison = comparison.replace("uniform sampler2D sampler;",
                                    "uniform sampler2D sampler;\nuniform bool uUnculled;")
    assert count == 1
    program = compile_program(fragment)
    reference = compile_program(comparison)
    try:
        assert reference.attributeLocation("position") == program.attributeLocation("position")
        for width, height, canvas_width, canvas_height, origin_x, origin_y, target_x, target_y in FIXTURES:
            image = QImage(width + 24, height + 32, QImage.Format_RGBA8888)
            image.fill(QColor("#fc00bd"))
            texture = QOpenGLTexture(image, QOpenGLTexture.DontGenerateMipMaps)
            texture.setMinificationFilter(QOpenGLTexture.Linear)
            texture.setMagnificationFilter(QOpenGLTexture.Linear)
            texture.bind(0)
            fbo = QOpenGLFramebufferObject(canvas_width, canvas_height)
            try:
                assert fbo.isValid() and fbo.bind()
                gl.glViewport(0, 0, canvas_width, canvas_height)
                values = {
                    "sampler": 0, "textureWidth": image.width(), "textureHeight": image.height(),
                    "uSeed": 17., "uViewX": -12. * canvas_width / width,
                    "uViewY": -14. * canvas_height / height,
                    "uViewWidth": image.width() * canvas_width / width,
                    "uViewHeight": image.height() * canvas_height / height,
                    "uOriginX": float(origin_x), "uOriginY": float(origin_y),
                    "uWindowWidth": float(width), "uWindowHeight": float(height),
                    "uPaddingX": 12., "uPaddingY": 14., "uTargetX": float(target_x),
                    "uTargetY": float(target_y), "uTargetSize": 36.,
                }
                configure(gl, reference, values)
                configure(gl, program, values)
                timings = []
                for progress in (.25, .5, .75):
                    texture.bind(0)
                    gl.glUniform1f(program.uniformLocation("uProgress"), progress)
                    gl.glDrawArrays(0x0004, 0, 6)
                    gl.glFinish()
                    for repeat in range(3):
                        query.begin()
                        gl.glDrawArrays(0x0004, 0, 6)
                        query.end()
                        timings.append(query.waitForResult() / 1e6)
                    optimized = fbo.toImage()
                    if progress == .25 and (target_x, target_y) == (60, 20):
                        for fraction in (.82, .9):
                            x = int((origin_x + width * fraction - values["uViewX"])
                                    / values["uViewWidth"] * canvas_width)
                            y = int((origin_y + height * fraction - values["uViewY"])
                                    / values["uViewHeight"] * canvas_height)
                            color = optimized.pixelColor(x, y).getRgb()
                            assert max(abs(a - b) for a, b in zip(color, (252, 0, 189, 255))) <= 1, (
                                width, height, progress, "Unreached source is distorted", color
                            )
                    # A uniform toggle keeps both paths in the same compiled program:
                    # separate programs can round source-cell boundaries differently.
                    assert fbo.bind() and reference.bind()
                    texture.bind(0)
                    gl.glUniform1f(reference.uniformLocation("uProgress"), progress)
                    gl.glUniform1i(reference.uniformLocation("uUnculled"), 0)
                    # Warm each path before taking the comparison readback.
                    for repeat in range(8):
                        gl.glDrawArrays(0x0004, 0, 6)
                    gl.glFinish()
                    optimized = fbo.toImage()
                    assert fbo.bind() and reference.bind()
                    texture.bind(0)
                    gl.glUniform1i(reference.uniformLocation("uUnculled"), 1)
                    for repeat in range(8):
                        gl.glDrawArrays(0x0004, 0, 6)
                    gl.glFinish()
                    expected = fbo.toImage()
                    delta = difference(optimized, expected)
                    if delta.max() > 1:
                        pixels = delta.reshape(optimized.height(), optimized.bytesPerLine() // 4, 4)
                        y, x, channel = np.unravel_index(pixels.argmax(), pixels.shape)
                        print("Culling mismatch:", (width, height), "target", (target_x, target_y),
                              "progress", progress, "pixel", (x, y), "channel", channel,
                              "optimized", optimized.pixelColor(x, y).getRgb(),
                              "unculled", expected.pixelColor(x, y).getRgb(),
                              "differing pixels", np.count_nonzero(pixels.max(axis=2) > 1),
                              flush=True)
                        raise AssertionError("Culling changes rendered fragments")
                    assert fbo.bind() and program.bind()
                assert gl.glGetError() == 0, "OpenGL rendering failed"
                print(f"{path.name}: {width}x{height} target ({target_x},{target_y}): "
                      f"median {statistics.median(timings):.2f} ms, max {max(timings):.2f} ms; "
                      "PASS: optimized pixels match unculled output", flush=True)
            finally:
                fbo.release()
                texture.destroy()
                del fbo, texture
    finally:
        for item in (program, reference):
            item.release()
            item.removeAllShaders()


def main():
    app = QGuiApplication([])
    fmt = QSurfaceFormat()
    fmt.setVersion(3, 3)
    fmt.setProfile(QSurfaceFormat.CoreProfile)
    context = QOpenGLContext()
    context.setFormat(fmt)
    assert context.create(), "Could not create a GPU context"
    surface = QOffscreenSurface()
    surface.setFormat(context.format())
    surface.create()
    assert context.makeCurrent(surface), "Could not make the GPU context current"
    gl = context.functions()
    print("Renderer:", gl.glGetString(0x1F01), flush=True)
    vao = QOpenGLVertexArrayObject()
    assert vao.create()
    vao.bind()
    buffer = QOpenGLBuffer(QOpenGLBuffer.VertexBuffer)
    assert buffer.create() and buffer.bind()
    vertices = struct.pack("12f", -1, -1, 1, -1, -1, 1, -1, 1, 1, -1, 1, 1)
    buffer.allocate(vertices, len(vertices))
    query = QOpenGLTimerQuery()
    assert query.create(), "GPU timer queries are not supported"
    status = 0
    try:
        for filename in sys.argv[1:] or [ROOT / "effect/contents/shaders/digital.frag"]:
            check_shader(gl, query, Path(filename))
    except Exception:
        traceback.print_exc()
        status = 1
    finally:
        # Let Qt delete the query exactly once, while its context is still current.
        del query, buffer, vao
        context.doneCurrent()
        surface.destroy()
        app.processEvents()
    if status == 0:
        print("PASS: GPU benchmark completed and resources released", flush=True)
    return status


if __name__ == "__main__":
    sys.exit(main())
