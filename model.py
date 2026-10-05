"""Image Studio's non-destructive composition and PNG rendering."""
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QImage, QPainter, QPainterPath, QColor, QPen, QFont, QFontMetricsF, QPainterPathStroker


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
    border_path = None
    if scene['border'] or scene.get('transparent_outside'):
        thickness = min(scene['border'] * width / output_width, min(width, height))
        inset = thickness / 2
        border_rect = rect.adjusted(inset, inset, -inset, -inset)
        border_shape = scene.get('border_shape', 'Follow crop')
        if border_shape != 'Follow crop':
            side = min(border_rect.width(), border_rect.height())
            border_rect = QRectF((width - side) / 2, (height - side) / 2, side, side)
        else:
            border_shape = shape
        border_path = QPainterPath()
        if border_shape == 'Circle':
            border_path.addEllipse(border_rect)
        elif border_shape in ('Rounded square', 'Rounded rectangle'):
            radius = max(0, min(scene.get('border_radius', min(output_width, output_height) * .12) * width / output_width, min(width, height) / 2) - inset)
            border_path.addRoundedRect(border_rect, radius, radius)
        else:
            border_path.addRect(border_rect)
    if scene.get('transparent_outside') and border_path is not None:
        stroke = QPainterPathStroker()
        stroke.setWidth(thickness)
        clip = clip.intersected(border_path.united(stroke.createStroke(border_path)))
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
    if scene['border'] and border_path is not None:
        painter.setPen(QPen(QColor(scene['border_color']), thickness))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(border_path)
    painter.end()
    return image
