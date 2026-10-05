# Image Studio for Playlite

Edit icons, covers, headers, and backgrounds from the Images page in Add Game or
Edit Game. Requires Playlite 0.2.39 or later, plugin API 1.

The pencil button beside each image's existing controls opens the downloader on
that image type. Choose downloaded artwork, Use current image, or Open image to
start from a local file. Apply the selection to open Image Studio.

Image Studio provides output/aspect presets, custom dimensions, fill/fit cropping,
drag-to-pan, mouse-wheel zoom, numeric zoom/pan controls, rotation, opacity,
transparent or colored backgrounds, crop shapes, and borders. Add image or text
overlays, select a layer to transform it, reorder/hide/remove overlays, or undo and
redo changes. Stock circle, square, and rounded-square borders fit inside the
canvas without changing its dimensions. Selecting a stock shape enables an 8px
border; adjust its thickness and color as needed. Borders can also follow the crop.
The blue frame shows exactly what will be exported.

Apply renders a PNG into a temporary folder and fills only the target image field.
Save the game in Playlite to keep it. Cancel leaves the existing image untouched;
original downloaded/local image files are never overwritten. Output is limited
to 4096 pixels per dimension. Projects/layers are kept for the editing session;
reopening an applied image starts from the flattened PNG.

Install/update via Settings → Plugins. The existing IconStudio plugin ID and
is retained for compatible updates; the displayed name is now
Image Studio. New installations are enabled by default; existing enable/disable
choices are preserved. Right-click the installed plugin to enable it, then restart
Playlite if needed.

Build locally with `python3 tools/build_release.py`. CI installs the core and
isolated plugin fixtures, runs tests, and publishes `plugin.zip` and `SHA256SUMS`
from version tags.
