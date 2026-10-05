"""Image Studio's non-destructive composition and PNG rendering."""
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QImage, QPainter, QPainterPath, QColor, QPen, QFont, QFontMetricsF, QLinearGradient, QTransform


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
    image_scale = max(.01, min(1, scene.get('image_size', 100) / 100))
    frame_scale = max(.01, min(1, scene.get('border_size', 100) / 100))
    rect = QRectF(width * (1 - image_scale) / 2, height * (1 - image_scale) / 2, width * image_scale, height * image_scale)
    frame_rect = QRectF(width * (1 - frame_scale) / 2, height * (1 - frame_scale) / 2, width * frame_scale, height * frame_scale)
    clip = QPainterPath()
    shape = scene['shape']
    if shape == 'Circle':
        clip.addEllipse(rect)
    elif shape == 'Rounded rectangle':
        radius = min(scene.get('border_radius', min(output_width, output_height) * .12) * width / output_width * image_scale, min(rect.width(), rect.height()) / 2)
        clip.addRoundedRect(rect, radius, radius)
    else:
        clip.addRect(rect)
    border_transform = QTransform()
    border_transform.translate(width / 2, height / 2)
    border_transform.rotate(scene.get('border_rotation', 0))
    border_transform.translate(-width / 2, -height / 2)
    border_path = None
    has_border_shape = scene.get('border_enabled', True) and scene.get('border_shape') != 'None'
    style = scene.get('border_style', 'Solid colour')
    border_width = scene['border'] * width / output_width if has_border_shape and style != 'None' else 0
    rim_width = border_width + 3 * width / output_width if border_width else 0
    if has_border_shape and (scene['border'] or scene.get('transparent_outside')):
        thickness = min(rim_width, min(frame_rect.width(), frame_rect.height()))
        inset = thickness / 2
        border_rect = frame_rect.adjusted(inset, inset, -inset, -inset)
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
            radius = max(0, min(scene.get('border_radius', min(output_width, output_height) * .12) * width / output_width * frame_scale, min(frame_rect.width(), frame_rect.height()) / 2) - inset)
            border_path.addRoundedRect(border_rect, radius, radius)
        else:
            border_path.addRect(border_rect)
        border_path = border_transform.map(border_path)
    if scene.get('transparent_outside') and border_path is not None:
        # Hide the image beneath the outer half of the frame's stroke.
        clip = clip.intersected(border_path)
    painter.setClipPath(clip)
    if scene['background'] != 'transparent':
        painter.fillRect(rect, QColor(scene['background']))
    def draw_layer(layer):
        if not layer['visible']:
            return
        painter.save()
        painter.setOpacity(layer['opacity'] / 100)
        if layer['base']:
            painter.translate(rect.x() + layer['x'] * rect.width(), rect.y() + layer['y'] * rect.height())
        else:
            painter.translate(layer['x'] * width, layer['y'] * height)
        painter.rotate(layer['rotation'])
        zoom = layer['zoom'] / 100
        if layer['image'] is not None:
            source = layer['image']
            if layer['base']:
                fit = min if scene['fit'] == 'Fit' else max
                scale = fit(rect.width() / source.width(), rect.height() / source.height()) * zoom
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
    for layer in scene['layers']:
        if layer['base']:
            draw_layer(layer)
    painter.setClipping(False)
    if border_width and border_path is not None:
        brush = QColor(scene['border_color'])
        if style in ('Silver', 'Gold', 'Dark metal'):
            light, mid = {'Silver': ('#ffffff', '#808080'),
                          'Gold': ('#fafad2', '#daa520'),
                          'Dark metal': ('#808080', '#373737')}[style]
            brush = QLinearGradient(border_transform.map(border_rect.topLeft()), border_transform.map(border_rect.bottomRight()))
            for position, color in ((0, light), (.35, mid), (.6, '#000000'), (1, light)):
                brush.setColorAt(position, QColor(color))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor('black'), thickness))
        painter.drawPath(border_path)
        painter.setPen(QPen(brush, min(border_width, thickness)))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(border_path)
    # Foreground overlays sit above the frame and are bounded only by the canvas.
    painter.setClipping(False)
    for layer in scene['layers']:
        if not layer['base']:
            draw_layer(layer)
    painter.end()
    return image
