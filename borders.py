"""Procedural vector border patterns and colour finishes."""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPen, QPainterPath, QPainterPathStroker, QLinearGradient

STYLES = ('Silver', 'Gold', 'Dark metal', 'Chrome', 'Brushed metal', 'Solid colour', 'None')
PATTERNS = ('Single rim', 'Double rim', 'Raised bevel', 'Recessed bevel', 'Glow', 'Dashed', 'Dotted', 'Corner brackets')
COLOURS = {'Silver': ('#ffffff', '#808080', '#000000'),
           'Gold': ('#fafad2', '#daa520', '#000000'),
           'Dark metal': ('#808080', '#373737', '#000000'),
           'Chrome': ('#ffffff', '#b0bac5', '#202630'),
           'Brushed metal': ('#e6e9ec', '#89939d', '#343b43')}
BORDER_KEYS = ('border_enabled', 'border_shape', 'border_style', 'border_pattern',
               'border_size', 'border_rotation', 'border', 'border_color',
               'border_highlight', 'border_midtone', 'border_shadow', 'border_rim_color',
               'border_gap', 'border_spacing', 'border_glow', 'border_bracket',
               'border_radius', 'transparent_outside')


def colours(scene):
    defaults = COLOURS.get(scene.get('border_style'), ('#ffffff', scene.get('border_color', '#ffffff'), '#000000'))
    return tuple(scene.get(key) or default for key, default in zip(
        ('border_highlight', 'border_midtone', 'border_shadow'), defaults))


def finish(scene, start, end):
    if scene.get('border_style') == 'Solid colour':
        return QColor(scene['border_color'])
    light, mid, dark = colours(scene)
    gradient = QLinearGradient(start, end)
    if scene.get('border_style') == 'Chrome':
        stops = ((0, light), (.35, mid), (.48, dark), (.5, light), (.65, mid), (1, light))
    elif scene.get('border_style') == 'Brushed metal':
        stops = [(0, light), (1, mid)]
        for i in range(1, 40):
            stops.append((i / 40, dark if i % 8 == 0 else mid if i % 2 else light))
    else:
        stops = ((0, light), (.35, mid), (.6, dark), (1, light))
    for position, colour in stops:
        gradient.setColorAt(position, QColor(colour))
    return gradient


def stroke_path(path, width):
    stroke = QPainterPathStroker()
    stroke.setWidth(max(.01, width))
    return stroke.createStroke(path)


def draw_border(painter, scene, path, rect, transform, width, thickness, scale):
    brush = finish(scene, transform.map(rect.topLeft()), transform.map(rect.bottomRight()))
    pattern = scene.get('border_pattern', 'Single rim')
    painter.save()
    painter.setBrush(Qt.BrushStyle.NoBrush)
    if pattern == 'Corner brackets':
        full_path, path = path, QPainterPath()
        fraction = scene.get('border_bracket', 20) / 100 / 8
        # Symmetric short sections around each corner (or quadrant on a circle).
        for corner in (0, .25, .5, .75):
            for i in range(33):
                point = full_path.pointAtPercent((corner - fraction + 2 * fraction * i / 32) % 1)
                if i == 0:
                    path.moveTo(point)
                else:
                    path.lineTo(point)
    if pattern == 'Glow':
        colour = QColor(scene.get('border_color', '#ffffff'))
        glow = scene.get('border_glow', 12) * scale
        for step in range(12, 0, -1):
            colour.setAlpha(round(70 * (1 - step / 13)))
            painter.setPen(QPen(colour, width + glow * step / 6))
            painter.drawPath(path)
    if pattern == 'Double rim':
        gap = min(scene.get('border_gap', 3) * scale, width * .8)
        bands = stroke_path(path, width).subtracted(stroke_path(path, gap))
        rim = stroke_path(path, thickness).subtracted(stroke_path(path, max(.01, gap - 3 * scale)))
        painter.fillPath(rim, QColor(scene.get('border_rim_color', '#000000')))
        painter.fillPath(bands, brush)
    elif pattern in ('Raised bevel', 'Recessed bevel'):
        light, _, dark = colours(scene)
        if pattern == 'Recessed bevel':
            light, dark = dark, light
        bevel = QLinearGradient(transform.map(rect.topLeft()), transform.map(rect.bottomRight()))
        for position, colour in ((0, light), (.49, light), (.51, dark), (1, dark)):
            bevel.setColorAt(position, QColor(colour))
        painter.setPen(QPen(QColor(scene.get('border_rim_color', '#000000')), thickness))
        painter.drawPath(path)
        painter.setPen(QPen(bevel, width))
        painter.drawPath(path)
    else:
        for colour, stroke_width in ((QColor(scene.get('border_rim_color', '#000000')), thickness), (brush, width)):
            pen = QPen(colour, stroke_width)
            if pattern in ('Dashed', 'Dotted'):
                spacing = max(.1, scene.get('border_spacing', 12) * scale / max(width, .01))
                # Use the same pixel lengths for the coloured stroke and outer rim.
                unit = max(width, .01) / stroke_width
                pen.setDashPattern(([3 * unit, spacing * unit] if pattern == 'Dashed' else [.01 * unit, spacing * unit]))
                pen.setCapStyle(Qt.PenCapStyle.RoundCap if pattern == 'Dotted' else Qt.PenCapStyle.FlatCap)
            painter.setPen(pen)
            painter.drawPath(path)
    painter.restore()
