"""Named border presets, stored independently of image editing sessions."""
import json
import os
import tempfile
from pathlib import Path
from .borders import BORDER_KEYS, STYLES, PATTERNS


def default_path(parent=None):
    root = getattr(parent, 'data', None)
    if root is None:
        root = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'playlite'
    return Path(root) / 'image-studio-border-presets.json'


def load_presets(path):
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise ValueError('The border presets file must contain named presets.')
    presets = {}
    for name, values in data.items():
        if not isinstance(values, dict):
            continue
        valid = {}
        for key, value in values.items():
            if key not in BORDER_KEYS:
                continue
            if key in ('border_enabled', 'transparent_outside'):
                if isinstance(value, bool):
                    valid[key] = value
            elif key in ('border_style', 'border_shape', 'border_pattern'):
                choices = STYLES if key == 'border_style' else PATTERNS if key == 'border_pattern' else ('None', 'Follow crop', 'Circle', 'Square', 'Rounded square')
                if value in choices:
                    valid[key] = value
            elif key.endswith(('color', 'highlight', 'midtone', 'shadow')):
                from PyQt6.QtGui import QColor
                if value is None or isinstance(value, str) and QColor(value).isValid():
                    valid[key] = value
            elif isinstance(value, int) and not isinstance(value, bool):
                limits = {'border_size': (1, 100), 'border_rotation': (-180, 180),
                          'border': (0, 100), 'border_radius': (0, 2048),
                          'border_gap': (0, 100), 'border_spacing': (1, 100),
                          'border_glow': (0, 100), 'border_bracket': (1, 100)}
                if key in limits:
                    lo, hi = limits[key]
                    valid[key] = max(lo, min(hi, value))
        presets[name] = valid
    return presets


def save_presets(path, presets):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + '.', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w') as stream:
            json.dump(presets, stream, indent=2, sort_keys=True)
            stream.write('\n')
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
