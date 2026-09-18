# Layout: plans to Companion configuration

Use a private `geometry.yaml` as the source for room polygons, node locations, and floor
alignment. The editor runs entirely offline and exports both the editable geometry and a
Companion `floors`/`nodes` fragment. It does not deploy configuration or measure tracking
accuracy. Validate the final placement with a walk test.

## Try the fictional example

From the repository root, with Python 3.11+ and PyYAML installed:

```sh
python tooling/layout/build_layout_page.py examples/geometry.example.yaml --out /tmp/layout-editor.html
python tooling/layout/emit_companion.py examples/geometry.example.yaml --out /tmp/companion.yaml
```

Open `/tmp/layout-editor.html` in a browser. No web server or internet connection is needed.
Choose another output path on systems without `/tmp`. The generated page is self-contained;
the source assets live in `tooling/layout/assets/`. Do not commit a generated page containing
private geometry or plan images. All example dimensions and positions are fictional, and
the three example nodes demonstrate the editor rather than recommend a deployment count.

## Describe your plans

Export one PNG per floor from a plan application, or photograph a dimensioned sketch.
Keep the images and geometry in your private configuration directory. Measure a labelled
length in pixels and divide by its length in metres to calculate `px_per_m`. Check a second
length to catch image distortion. Pick a pixel as the floor's local origin; pixel y increases
downward, while geometry y increases upward.

```yaml
bounds: [[0, 0], [10, 8]]
floors:
  - id: ground
    name: Ground floor
    z: [0, 3]
    local: {w: 10, h: 8}
    # Optional; these invented image values are only a schema illustration.
    image: {file: plans/ground.png, px_per_m: 80, origin_px: [40, 680]}
    place: {flip_h: false, flip_v: false, dx: 0, dy: 0}
    rooms:
      entry: [[0, 0], [4, 0], [4, 8], [0, 8]]
    nodes:
      entry: [1, 1, 0.5]
```

- `bounds`: house-frame minimum and maximum `[x, y]` in metres.
- `floors`: nonempty list with unique string `id` values and optional display `name`.
- `z`: absolute floor base and ceiling. A node's third coordinate is relative to the base.
- `local`: positive width and height used as the flip axes for this floor's plan.
- `place`: mirror locally around width/height, then add house offsets `dx`/`dy`.
- `rooms`: room-id mapping to polygons of at least three local `[x, y]` vertices.
- `nodes`: globally unique node-id mapping to local `[x, y, relative_z]` points. Use the
  configured ESPresense node identifier. Height must fall inside the floor's z range.
- `image`: optional local PNG file, relative to `geometry.yaml`, its scale, and origin pixel.
  Remote image URLs are rejected. The builder embeds the PNG bytes, so the page needs no
  access to the original image once built.

Numeric values must be finite. Geometry uses JSON-compatible YAML values; keep custom
metadata to ordinary mappings, lists, strings, numbers, booleans and null. For example, quote
dates. Comments, YAML anchors and formatting are not preserved; values and custom metadata
are preserved in the geometry export. Optional `place`, `rooms`, and `nodes` fields receive
defaults when omitted.

## Place and align

```sh
python tooling/layout/build_layout_page.py /path/to/private/geometry.yaml --out /path/to/private/layout-editor.html
```

Each floor has its own map using a shared house coordinate frame. The dashed rectangle marks
the source bounds. Flip and offset controls move the plan image, room outlines and nodes
together. These controls do not rewrite the local coordinates, so a node placed on an outlet
stays on that outlet as its floor is aligned.

Drag a node, or focus its dot with Tab and use arrow keys to move 5 cm in the visible house
frame. Hold Shift for 25 cm. Select a node using its dropdown to change its height above the
floor. The adjacent readout shows the absolute house x/y/z that Companion receives.

**Download geometry.yaml** saves the complete edited source: local node positions, relative
heights, placement transforms, room polygons, image references and extra metadata. Replace
your private source with that download and rebuild the page, or import it into the editor.
Never paste Companion absolute node points into geometry's local-coordinate `nodes` block.

**Import geometry.yaml** accepts YAML or JSON locally. Each import clears embedded plan
images because a matching filename cannot prove it is the same image. The page explicitly
shows when the plan is missing; rebuild with the CLI to embed the imported source's PNGs.
Room outlines and nodes remain editable without an image.

Draft persistence is opt-in with **Save draft in this browser**. Drafts are keyed to the
source data, validated before restoring, and never sent to a server. Storage availability
for `file:` pages varies by browser. If storage is blocked/full, the editor remains usable
and asks you to download the source. Uncheck the box to remove the saved draft. **Reset to
imported source** discards the current edits and restores the source loaded by this page.
Always download the geometry before closing if you need a portable copy.

## Export to Companion

**Copy Companion YAML** copies the displayed `floors` and `nodes`; the download button saves
the same fragment. If clipboard access is unavailable, the page selects the output so you
can copy it with Ctrl+C. The equivalent CLI is:

```sh
python tooling/layout/emit_companion.py /path/to/private/geometry.yaml --out /path/to/private/companion/floors-and-nodes.yaml
```

Merge those two keys into your private Companion configuration, retaining its broker,
devices, filtering and other settings. The emitter produces per-floor 3D `bounds`, nested
room `points`, and absolute node `point` values with a `floors` list. A node whose id matches
a room id also gets that `room`. For example, a 1.2 m node on a floor beginning at z=3 has
absolute z=4.2. Derived coordinates suppress floating-point noise at ten decimal places;
geometry source values are not rounded on export.

Exports expand x/y bounds to include the original house bounds plus every transformed
floor footprint, room vertex and node. Moving a floor or node outside the initial bounds
therefore does not silently exclude it from Companion's search area. Source bounds stay
unchanged in the editable geometry file.

Schema checked against the [official Companion configuration documentation](https://espresense.com/companion/configuration/)
on 2026-09-18. Its default `map.flip_y: true` uses a bottom-left origin. Physical placement
and radio overlap determine location quality; current upstream guidance aims for at least
five fixes. A mathematically sufficient node count alone does not establish reliable
coverage. Spread receivers, test each relevant room and doorway, and validate with the
actual device. This editor makes no accuracy guarantee.

## Development verification

```sh
python -m unittest discover -s tests -p 'test_layout.py'
npm install --prefix /tmp/espresense-browser --no-package-lock playwright@1.57.0
/tmp/espresense-browser/node_modules/.bin/playwright install --with-deps chromium
NODE_PATH=/tmp/espresense-browser/node_modules node tests/test_layout_browser.cjs
```

Run builds and tests on the project's execution host. The browser test builds its own
fictional geometry and a synthetic PNG in a temporary directory. It exercises dragging,
keyboard movement under flips, offsets, height, draft reload/isolation, import validation,
image provenance, geometry roundtrip, Companion parity with Python, offline requests and
mobile overflow. It prints the screenshot location; set `LAYOUT_SCREENSHOT` to choose one.

The browser YAML parser is vendored **js-yaml 4.1.1**, from its upstream npm package
[`nodeca/js-yaml`](https://github.com/nodeca/js-yaml), with the MIT license at
`tooling/layout/assets/js-yaml.LICENSE`. The minified asset SHA-256 is
`0de3dec92d20eab9e0b46a5d928cd45ec025d73e348ddf458dbfb01da00cb473`.
It is embedded at build time; there are no runtime CDN dependencies.
