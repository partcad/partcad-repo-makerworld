# MakerWorld for PartCAD

Serves MakerWorld's models as PartCAD parts, published as
`//pub/universe/makerworld/models`.

**Nothing is listed.** A model site's catalog is not something to enumerate,
so `pc list parts` of this package is empty, as is `pc list packages`. A part is
asked for by name, and found with `pc search parts`:

```shell
pc search parts -P //pub/universe/makerworld/models -k "cable clip"
pc inspect "//pub/universe/makerworld/models:1000000"
```

**No geometry is vendored.** Every file is fetched from MakerWorld the first
time a part is built, and kept by PartCAD from then on.

**Nothing here is manufacturable.** The package says `manufacturable: false`,
and so does the plugin of what it serves: an upload to a model site says
nothing about whether, or how, it is made to be made.

Requires PartCAD 0.9.3 or newer: the first release whose repository plugins
may search their own catalog (`searchKinds`), resolve a parametrized name
themselves (`instanceKinds`), and log in (`pc login`). They are described under
"Repositories" and "Logging in" in PartCAD's plugin documentation.

## Names

A model is a part per file of it that PartCAD reads, and the name says which.
A model is named by the model's number, as in `makerworld.com/en/models/1000000`:

| Name | Is |
| --- | --- |
| `1000000` | the model's best file |
| `1000000;format=stl` | its best STL |
| `1000000;file=<name>` | one file the designer uploaded, by its name (`extras/base.3mf` in a folder) |
| `1000000;file=preview-<profile>` | the preview mesh of one print profile, by the profile's number |

Both parameters may be given, and must then agree. "Best" is by format, in
this order, and among files of one format the first the site lists:

| Format | Read as PartCAD part type | Extensions |
| --- | --- | --- |
| `step` | `step` | `.step`, `.stp` |
| `brep` | `brep` | `.brep`, `.brp` |
| `3mf` | `3mf` | `.3mf` |
| `stl` | `stl` | `.stl` |
| `obj` | `obj` | `.obj` |
| `glb` | `gltf` | `.glb` |
| `scad` | `scad` | `.scad` |

An exact boundary representation beats a mesh of it, and 3MF knows its units
where STL does not. A `.gltf` is not served, since the buffers it names beside
itself do not come with it; an OpenSCAD source is last, because on a model site
it is usually the customizable source of the meshes beside it. A file in any
other format - IGES, SolidWorks, Fusion, a picture - is not a part. A name
that asks for one, or for a file the model has not got, is not found, and the
plugin says why.

These names are resolved by the plugin rather than by PartCAD applying the
parameters to a base part, because another file is another `path` and maybe
another `type`. `pc info` of a part shows the `file` and `format` it resolved
to, which is what to write to pin it: the best file of a model can change when
its designer uploads another.

## Search

`pc search parts -k <words>` asks MakerWorld's own search, and answers with
names of the form above - one per file, so a hit is everything needed to fetch
its geometry. Two files that differ only in their extension (`clip.step`,
`clip.stl`) are one part in two formats, and only the better is named; a model
with no file PartCAD reads is not a hit. `--limit` caps the hits (20 by
default); the plugin asks the site for three times as many models, and reads
their file lists a few at a time until it has enough.

A search is never cached by PartCAD; the plugin keeps what the site answered for
ten minutes.

## Logging in

```shell
pc login //pub/universe/makerworld:makerworld_repo
```

checks the token the plugin has by asking Bambu Lab's cloud API whom it belongs
to (`api.bambulab.com/v1/user-service/my/profile`, the account MakerWorld signs
in with), and keeps it if it still works. Otherwise it opens your default
browser, in PartCAD's own profile with PartCAD's extension in it, on MakerWorld.
Sign in with your Bambu Lab account; the extension takes the `token` cookie
MakerWorld keeps for a signed-in user - only something shaped like the JWT it
is, so nothing a visitor has can be taken for it - and closes the window. The
token is saved in your `~/.partcad/config.yaml` as your override of the
repository's `token` parameter. `pc login --check ...` only checks it.

## Credentials, by hand

A model's details are MakerWorld's to give anyone, and so is the mesh its viewer
shows of each print profile. Those are served without a sign-in: each print
profile's preview is a part of its own, `<model>;file=preview-<profile id>`, a
`.glb` of the profile's plate. The files the designer uploaded take a signed-in
MakerWorld (Bambu Lab) account. Give the plugin its access token either way,
never in a package:

```shell
export MAKERWORLD_TOKEN=...       # read by the plugin; see the note on Docker below
```

```yaml
# ~/.partcad/config.yaml
parameters:
  "//pub/universe/makerworld:makerworld_repo":
    token: "..."
```

The token is sent as a bearer token to `makerworld.com`'s own API, and to
nothing else.

**What a model's best file is depends on whether there is a token.** Without
one, it is the default print profile's preview (a preview is only ever chosen
when nothing else can be had); with one, it is the best file the designer
uploaded. PartCAD keeps what a name resolved to, so after adding a token, ask by
`file=` or `format=`, or refresh the package (`pc update`), to have the
uploaded files.

### The preview mesh

MakerWorld compresses its previews with Draco (`KHR_draco_mesh_compression`,
marked required), which PartCAD's glTF reader does not decode. The plugin writes
each such mesh out as the plain triangles it holds before PartCAD reads it,
keeping the file's nodes, units and orientation; normals, colours and textures
are dropped. That takes [DracoPy](https://pypi.org/project/DracoPy/), which the
package declares in `pythonRequirements`, so PartCAD installs it into the
sandbox the plugin runs in. A preview is of the whole plate, as sliced: every
object on it, where the profile put it.

**Docker.** PartCAD runs a plugin in its Python sandbox, and the `docker` sandbox
does not carry PartCAD's environment into its container, so an environment
variable does not reach the plugin there. The repository parameter does, being
part of what PartCAD hands the plugin; use that, or `pythonSandbox: venv`.

## Status

Run end to end against the live site with PartCAD: a model's details, its print
profiles' previews (decoded and built, `1000000` comes out as the 31.5 x 31.5 x
3.6 mm lens cap it is) and the choice of file with and without a token. Three
things could not be run from where it was written, and are written to what is
known of them:

- **Search** asks `/api/v1/search-service/select/design/nav`, which is what the
  site's search page asks. Cloudflare answered it with a bot check there, which
  the plugin reports as one; the answer's shape is read leniently (the models
  are looked for under `hits`, `items`, `designs`, `list` or `data`).
- **The designer's files** are asked of `/api/v1/design-service/design/<id>/model`
  with the token, which answers anyone else "Please log in to download models";
  the plugin expects `{"url": ...}` of an archive of them, or of the one file.
- **The token** is sent as `Authorization: Bearer`, as Bambu Lab's cloud API
  takes it.

`pc login` was run against the live site in a real (headed) Chrome with
PartCAD's extension. MakerWorld sometimes puts Cloudflare's "Verify you are
human" in front of its pages; the extension's bar then asks the person to
confirm it, and nothing else - nothing clicks it, and the plugin is handed
only the `token` cookie signing in leaves. When the page itself loads, its "Log
In" is a button only its text tells apart, which is what the guide picks it out
by. Signing in itself was not done, for want of an account.

## Layout

| Path | Purpose |
| --- | --- |
| `partcad.yaml` | `//pub/universe/makerworld`; the `models` external dependency and the `makerworld_repo` repository that serves it. |
| `makerworld_repo.py` | The repository plugin: how MakerWorld is asked. |
| `remote_models.py` | What every model-site plugin shares, byte for byte: the names, the formats, HTTP and its cache, the keys PartCAD asks. The same file is in partcad-repo-thingiverse, partcad-repo-makerworld, partcad-repo-grabcad, partcad-repo-printables and partcad-repo-cults3d; `remote_models.sha256` is its digest, and a test fails when the two disagree - change it in all five. |
| `test_*.py` | The tests. Nothing in them touches the network. |

```shell
python -m pytest
```

When what the plugin answers changes - here or in `remote_models.py` - raise
`CACHE_VERSION` in `makerworld_repo.py`: PartCAD keys everything it caches of this
package on it.

## Caching

PartCAD keeps every answer the plugin gives, files included, under its own
cache, apart from a search. The plugin keeps what MakerWorld answered under
`~/.cache/partcad-makerworld/` (or `$PARTCAD_MAKERWORLD_CACHE`): a model's details for
half an hour, since they carry links to its previews signed for an hour; a search for ten minutes, and a request that came to nothing for a while
too, so that a refused or throttled run is not repeated in full by the next one
- a 404 for a day, anything else for five minutes. Delete the directory to start
over.

Every request says what it is: `User-Agent: Mozilla/5.0 (compatible;
PartCAD-makerworld/<version>; +https://github.com/partcad/partcad-repo-makerworld)`.

## Licensing

The code here is Apache-2.0 (`LICENSE`). Each model carries its own licence (Creative Commons or MakerWorld's own), which the part states (`license`); it is the designer's, not this package's. MakerWorld's terms of use
are at <https://makerworld.com/en/terms-of-use>.
