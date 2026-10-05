# Image Studio for Playlite

Edit icons, covers, headers, and backgrounds from the Images page in Add Game or
Edit Game. Requires Playlite 0.2.40 or later, plugin API 1.

The pencil button beside each image's existing controls opens Image Studio directly
on that image. Empty image fields start with a transparent canvas. Download image…
at the bottom right opens the downloader on the matching image type to replace
the source. Replacement preserves the output, borders, and overlays and can be
undone. Canceling the downloader keeps the current image.

The workflow is Image → optional Border → optional Overlays → Output:

- Image contains its own sizing, corner radius, scale, position, rotation, opacity,
  background, replacement, and reset controls. Radius zero gives square corners;
  maximum radius gives a circle on a square canvas.
- Enable border is off initially. Enabling it reveals the visual style picker,
  thickness, colour, and Trim image outside border. It follows the crop by default;
  additional shapes are available. Silver, Gold, Dark metal, Solid colour, and None
  match the original Playnite Icon Studio vector rims. Disabling a border retains
  its settings for re-enabling and does not change the source crop.
- Overlays starts empty; Add image opens Logos in the downloader, and Add text
  creates a text overlay. The list contains overlays only, with visibility toggles.
  Selecting one reveals its separate transform, reorder, remove, and reset controls;
  text options appear only for text overlays. Foreground overlays extend beyond
  the border, up to the output edges.
- Output provides aspect/size presets and custom dimensions. Numeric controls use
  sliders with visible values; each drag is one undo step.

Dragging or scrolling the preview edits the selected overlay, or the image when
none is selected. The label below the preview names the active target. Adjusting
an Image control returns preview interactions to the image. Undo/Redo remain
available in the footer, beside Download image, Apply, and Cancel.

Apply renders a PNG into a temporary folder and fills only the target image field.
Save the game in Playlite to keep it. Cancel leaves the existing image untouched;
original downloaded/local image files are never overwritten. Output is limited
to 4096 pixels per dimension. Projects/layers are kept for the editing session;
reopening an applied image starts from the flattened PNG.

Install/update via Settings → Plugins. The existing IconStudio plugin ID
is retained for compatible updates; the displayed name is now
Image Studio. New installations are enabled by default; existing enable/disable
choices are preserved. Right-click the installed plugin to enable it, then restart
Playlite if needed.

Build locally with `python3 tools/build_release.py`. CI installs the core and
isolated plugin fixtures, runs tests, and publishes `plugin.zip` and `SHA256SUMS`
from version tags.
