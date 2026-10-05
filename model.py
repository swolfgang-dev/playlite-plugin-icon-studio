"""Image Studio's non-destructive composition and PNG rendering."""
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QImage, QPainter, QPainterPath, QColor, QPen, QFont, QFontMetricsF

PRESETS = {'Icon': (256, 256), 'CoverImage': (600, 900),
           'HeaderImage': (1920, 620), 'BackgroundImage': (1920, 1080)}


def image_layer(image, name='Image', base=False):
    if image.isNull():
        raise ValueError('This file could not be opened as an image.')
    return dict(image=image, name=name, base=base, text='', x=.5, y=.5,
                zoom=100, rotation=0, opacity=100, visible=True, color='#ffffff', text_size=48)


def render_scene(scene, width=None, height=None):
    output_width, output_height = scene['size']
    width, height = width or output_width, height or output_height
    if not (1 <= width <= 4096 and 1 <= height <= 4096):
        raise ValueError('Output dimensions must be between 1 and 4096 pixels.')
    image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
    rect = QRectF(0, 0, width, height)
    clip = QPainterPath()
    shape = scene['shape']
    if shape == 'Circle':
        clip.addEllipse(rect)
    elif shape == 'Rounded rectangle':
        clip.addRoundedRect(rect, min(width, height) * .12, min(width, height) * .12)
    else:
        clip.addRect(rect)
    painter.setClipPath(clip)
    if scene['background'] != 'transparent':
        painter.fillRect(rect, QColor(scene['background']))
    for layer in scene['layers']:
        if not layer['visible']:
            continue
        painter.save()
        painter.setOpacity(layer['opacity'] / 100)
        painter.translate(layer['x'] * width, layer['y'] * height)
        painter.rotate(layer['rotation'])
        zoom = layer['zoom'] / 100
        if layer['image'] is not None:
            source = layer['image']
            if layer['base']:
                fit = min if scene['fit'] == 'Fit' else max
                scale = fit(width / source.width(), height / source.height()) * zoom
            else:
                scale = width * .35 / source.width() * zoom
            w, h = source.width() * scale, source.height() * scale
            painter.drawImage(QRectF(-w / 2, -h / 2, w, h), source)
        else:
            font = QFont('Sans Serif')
            font.setPixelSize(max(1, round(layer['text_size'] * width / output_width * zoom)))
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QColor(layer['color']))
            bounds = QFontMetricsF(font).boundingRect(layer['text'])
            painter.drawText(QRectF(-bounds.width() / 2 - 4, -bounds.height() / 2 - 4,
                                   bounds.width() + 8, bounds.height() + 8), Qt.AlignmentFlag.AlignCenter, layer['text'])
        painter.restore()
    if scene['border']:
        painter.setPen(QPen(QColor(scene['border_color']), scene['border'] * width / output_width))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(clip)
    painter.end()
    return image
