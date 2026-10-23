# Fe₂S₂ resource-plot video

Everything needed to reproduce the current animation is included here:
the renderer, exact numerical snapshot, timing, fonts, logos and MP4 encoder.
The corresponding gate programs and reference tables are in [`../circuits`](../circuits/).

The reference video is [fe2s2_panel_a_animated.mp4](reference/fe2s2_panel_a_animated.mp4).
There is also a [GIF](reference/fe2s2_panel_a_animated.gif) and a
[final-frame PNG](reference/fe2s2_panel_a_compact.png), SVG and PDF.
The MP4 is 2160 × 1680 at 25 fps, lasting 12.64 seconds; the GIF is 1080 × 840.

## Install and run

From this directory, with Python 3.11:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python render.py --preview-only
python render.py
```

On Windows, activate with `.venv\Scripts\activate` instead. On macOS the
default MP4 encoder is Swift/AVFoundation (Xcode Command Line Tools).
On Linux and Windows, install FFmpeg with the `libx264` encoder and put
`ffmpeg` on `PATH`. To choose it explicitly:

```sh
python render.py --encoder ffmpeg
```

The GIF needs no external encoder:

```sh
python render.py --gif-only
```

Outputs go into `output/`, leaving the reference files intact. Set `--output`
to choose another directory. The Python dependencies, Rubik files and original
Swift encoder are pinned. MP4 bytes may differ across encoder/platform versions;
PDF/SVG metadata may also differ. Compare decoded frames and numerical values,
not only compressed-file hashes, when using a different platform.

[`reproduction_checks.json`](reproduction_checks.json) records the tested
macOS run: byte-identical PNG and GIF, matching MP4 properties, and three
pixel-identical decoded MP4 frames. The FFmpeg alternative is included but
was not exercised in that environment.

## Check the data

```sh
python check_data.py --recount
python ../verify.py
```

The first command counts the complete gate streams for the 24 displayed points.
The second also tests all 31 packaged circuits against the pinned reference
table. Neither command requires plotting libraries. `plot_data.json` maps each
video point to its circuit ID and includes the exact count, space, product,
axis limits and marker onset time. Hidden points from the wider plot do not
appear in this data; their original scheduling gaps are preserved.

The current legend has salmon circles for paper-method Frame SELECT, salmon
filled diamonds for Frame SELECT with shared optimizations, and yellow hollow
squares for PAU. The salmon cross is the released reference. Multiple-family
PAU points are omitted from this video; their seven gate programs remain available
in the circuit directory. The exact best PAU rectangle endpoint replaces its
nearby overlapping display representative.

## Files

- `render.py`: figure layout, rounded symbols and staged animation.
- `check_data.py`: mapping and optional gate-resource recount.
- `plot_data.json`: numerical inputs and exact timing.
- `plot.mplstyle`: bundled base plotting style.
- `encode_panel_video.swift`: macOS H.264 encoder; FFmpeg is an alternative.
- `requirements.txt`: pinned Python plotting dependencies.
- `assets/fonts/`: Rubik regular, italic and bold, with its OFL license.
- `assets/logos/`: the three logos used by the original figure.
- `reference/`: original outputs, hashes and outreach alt text.

The resource boundary and attribution are described in the [parent README](../README.md)
and [circuit notices](../circuits/NOTICE.md). Logos identify the series and do
not imply endorsement or attribute all shared optimizations to one method.
