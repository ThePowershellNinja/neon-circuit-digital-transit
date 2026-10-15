"""Render original synthetic content through the shipped shader, never a screen capture."""

import argparse
from pathlib import Path
import struct

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageSequence
from PySide6.QtGui import QGuiApplication, QImage, QOffscreenSurface, QOpenGLContext, QSurfaceFormat
from PySide6.QtOpenGL import (
    QOpenGLBuffer, QOpenGLFramebufferObject, QOpenGLShader, QOpenGLShaderProgram,
    QOpenGLTexture, QOpenGLVertexArrayObject,
)


ROOT = Path(__file__).resolve().parents[1]
WIDTH, HEIGHT = 1200, 780
WINDOW_WIDTH, WINDOW_HEIGHT = 700, 440
ORIGIN = (350, 140)
TARGET = (174, 702, 48, 44)
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


def font(size):
    return ImageFont.load_default(size=size)


def synthetic_window():
    image = Image.new("RGBA", (WINDOW_WIDTH, WINDOW_HEIGHT), "#192431")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 699, 47), fill="#263647")
    draw.text((22, 14), "Signal workspace", font=font(21), fill="#ecf4fa")
    for x in (620, 644, 668):
        draw.ellipse((x, 19, x + 9, 28), fill="#7295aa")
    draw.text((26, 72), "DIGITAL TRANSIT", font=font(30), fill="#d7f9ed")
    draw.text((27, 112), "Original synthetic content / no captured applications",
              font=font(16), fill="#98adbf")
    draw.rounded_rectangle((26, 154, 440, 328), radius=10, fill="#101b27")
    for row in range(5):
        y = 176 + row * 29
        draw.text((44, y), f"0{row + 1}", font=font(15), fill="#7295aa")
        draw.line([(80, y + 9), (130 + row * 29, y + 9),
                   (148 + row * 29, y - 2), (380, y - 2)],
                  fill=("#75e7d7" if row % 2 else "#a2e76e"), width=3)
        draw.ellipse((375, y - 7, 385, y + 3), fill="#75e7d7")
    for index, label in enumerate(("FLOW", "FRAGMENTS", "RESTORE")):
        y = 158 + index * 59
        draw.rounded_rectangle((462, y, 674, y + 45), radius=7, fill="#263647")
        draw.text((476, y + 13), label, font=font(16), fill="#d7f9ed")
        draw.ellipse((643, y + 16, 655, y + 28), fill="#a2e76e")
    draw.text((27, 354), "Independent paths. A coherent peeling wave.",
              font=font(22), fill="#ecf4fa")
    draw.rectangle((27, 397, 674, 405), fill="#304455")
    draw.rectangle((27, 397, 475, 405), fill="#75e7d7")
    return image


def background():
    image = Image.new("RGBA", (WIDTH, HEIGHT), "#111923")
    draw = ImageDraw.Draw(image)
    draw.text((46, 30), "Neon Circuit Digital Transit", font=font(34), fill="#e3edf5")
    draw.text((48, 79), "MINIMIZE / RESTORE", font=font(16), fill="#81a0b5")
    draw.rounded_rectangle((46, 688, 1154, 759), radius=15, fill="#1f2b39")
    x, y, width, height = TARGET
    draw.rounded_rectangle((x, y, x + width, y + height), radius=9, fill="#304b59")
    draw.rectangle((x + 11, y + 11, x + 37, y + 31), outline="#a2e76e", width=2)
    draw.line((x + 17, y + 36, x + 31, y + 36), fill="#75e7d7", width=2)
    draw.text((247, 706), "Illustrative shader render | synthetic window",
              font=font(17), fill="#c7d8e4")
    draw.text((247, 731), "Slowed for clarity; 300 ms base duration in KWin",
              font=font(14), fill="#81a0b5")
    return image


def render(output):
    app = QGuiApplication([])
    fmt = QSurfaceFormat()
    fmt.setVersion(3, 3)
    fmt.setProfile(QSurfaceFormat.CoreProfile)
    context = QOpenGLContext()
    context.setFormat(fmt)
    if not context.create():
        raise RuntimeError("Could not create an OpenGL context")
    surface = QOffscreenSurface()
    surface.setFormat(context.format())
    surface.create()
    if not context.makeCurrent(surface):
        raise RuntimeError("Could not make the offscreen context current")
    gl = context.functions()
    print("Renderer:", gl.glGetString(0x1F01), flush=True)
    vao = QOpenGLVertexArrayObject()
    assert vao.create()
    vao.bind()
    buffer = QOpenGLBuffer(QOpenGLBuffer.VertexBuffer)
    assert buffer.create() and buffer.bind()
    vertices = struct.pack("12f", -1, -1, 1, -1, -1, 1, -1, 1, 1, -1, 1, 1)
    buffer.allocate(vertices, len(vertices))
    fragment = (ROOT / "effect/contents/shaders/digital.frag").read_text()
    fragment = fragment.replace('#include "colormanagement.glsl"', COLOR_FUNCTIONS)
    program = QOpenGLShaderProgram()
    assert program.addShaderFromSourceCode(QOpenGLShader.Vertex, VERTEX), program.log()
    assert program.addShaderFromSourceCode(QOpenGLShader.Fragment, fragment), program.log()
    assert program.link() and program.bind(), program.log()
    program.enableAttributeArray("position")
    program.setAttributeBuffer("position", 0x1406, 0, 2, 8)
    original = synthetic_window()
    pixels = original.tobytes()
    source = QImage(pixels, WINDOW_WIDTH, WINDOW_HEIGHT, QImage.Format_RGBA8888)
    # Mirror the upload to match KWin's bottom-up redirected window texture.
    texture = QOpenGLTexture(source.mirrored(), QOpenGLTexture.DontGenerateMipMaps)
    texture.setMinificationFilter(QOpenGLTexture.Linear)
    texture.setMagnificationFilter(QOpenGLTexture.Linear)
    texture.bind(0)
    fbo = QOpenGLFramebufferObject(WIDTH, HEIGHT)
    assert fbo.isValid() and fbo.bind()
    gl.glViewport(0, 0, WIDTH, HEIGHT)
    values = {
        "sampler": 0, "textureWidth": WINDOW_WIDTH, "textureHeight": WINDOW_HEIGHT,
        "uSeed": 17., "uViewX": 0., "uViewY": 0.,
        "uViewWidth": float(WIDTH), "uViewHeight": float(HEIGHT),
        "uOriginX": float(ORIGIN[0]), "uOriginY": float(ORIGIN[1]),
        "uWindowWidth": float(WINDOW_WIDTH), "uWindowHeight": float(WINDOW_HEIGHT),
        "uPaddingX": 0., "uPaddingY": 0.,
        "uTargetX": TARGET[0] + TARGET[2] / 2, "uTargetY": TARGET[1] + TARGET[3] / 2,
        "uTargetSize": float(min(TARGET[2:])),
    }
    for name, value in values.items():
        location = program.uniformLocation(name)
        assert location >= 0, name
        if isinstance(value, int):
            gl.glUniform1i(location, value)
        else:
            gl.glUniform1f(location, value)
    frames = []
    base = background()
    for step in range(25):
        assert fbo.bind() and program.bind()
        texture.bind(0)
        gl.glUniform1f(program.uniformLocation("uProgress"), step / 24)
        gl.glDrawArrays(0x0004, 0, 6)
        image = fbo.toImage().convertToFormat(QImage.Format_RGBA8888)
        layer = Image.frombytes("RGBA", (WIDTH, HEIGHT), bytes(image.constBits()))
        if step == 0:
            crop = np.array(layer.crop((*ORIGIN, ORIGIN[0] + WINDOW_WIDTH,
                                        ORIGIN[1] + WINDOW_HEIGHT))).astype(int)
            assert np.abs(crop - np.array(original).astype(int)).max() <= 1, (
                "GPU preview does not preserve the synthetic window's orientation/content"
            )
        if step == 24:
            assert layer.getchannel("A").getextrema() == (0, 0)
        frames.append(Image.alpha_composite(base, layer).convert("RGB"))
    assert gl.glGetError() == 0
    fbo.release()
    texture.destroy()
    program.release()
    program.removeAllShaders()
    del fbo, texture, program, buffer, vao
    context.doneCurrent()
    surface.destroy()
    app.processEvents()
    output.mkdir(parents=True, exist_ok=True)
    frames[11].save(output / "preview.png", optimize=True)
    sequence = frames + list(reversed(frames[:-1]))
    durations = [600] + [40] * 23 + [300] + [40] * 23 + [600]
    assert len(sequence) == len(durations)
    sequence[0].save(output / "preview.gif", save_all=True, append_images=sequence[1:],
                     duration=durations, loop=0, optimize=True, disposal=2)
    with Image.open(output / "preview.gif") as animation:
        # GIF encoders coalesce identical resting frames.
        encoded = [frame.convert("RGB").tobytes() for frame in ImageSequence.Iterator(animation)]
        assert len(encoded) > 1 and encoded == list(reversed(encoded))
    print(f"Saved {output / 'preview.gif'} and {output / 'preview.png'}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "docs")
    render(parser.parse_args().output)
