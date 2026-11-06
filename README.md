# MakerWorld for PartCAD

Serves MakerWorld's models as PartCAD parts, published as
`//pub/collection/makerworld/models`.

**Nothing is listed.** A model site's catalog is not something to enumerate,
so `pc list parts` of this package is empty, as is `pc list packages`. A part is
asked for by name, and found with `pc search parts`:

```shell
pc search parts -P //pub/collection/makerworld/models -k "cable clip"
pc inspect "//pub/collection/makerworld/models:1000000"
```

**No geometry is vendored.** Every file is fetched from MakerWorld the first
time a part is built, and kept by PartCAD from then on.

**Nothing here is manufacturable.** The package says `manufacturable: false`,
and so does the plugin of what it serves: an upload to a model site says
nothing about whether, or how, it is made to be made.

Requires PartCAD 0.9.4 or newer: the first release whose repository plugins
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
| `1000000;source=preview` | the preview mesh of its first print profile, which needs no login |
| `1000000;file=preview-<profile>` | the preview mesh of one print profile, by the profile's number |

Any of them may be given together, and must then agree; `source` and the
plugin's own `formats` are under [Parameters](#parameters). "Best" is by
format, in this order unless `formats` says otherwise, and among files of one format the first the site lists:

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
pc login //pub/collection/makerworld:makerworld_repo
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
  "//pub/collection/makerworld:makerworld_repo":
    token: "..."
```

The token is sent as a bearer token to `makerworld.com`'s own API, and to
nothing else.

**What a model's best file is depends on whether there is a token.** Without
one, it is the default print profile's preview (a preview is only ever chosen
when nothing else can be had, unless asked for: `source=preview`); with one, it
is the best file the designer uploaded. A token `pc login` saved, or one set in
`~/.partcad/config.yaml`, is part of what PartCAD keys its cache of this package
on, so a name resolves afresh once it is there; after setting `MAKERWORLD_TOKEN`
instead, `pc update` refreshes it.

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

## Parameters

The plugin's parameters, declared in `partcad.yaml`, are a default for every
MakerWorld part:

| Parameter | Default | What it is |
| --- | --- | --- |
| `formats` | all, in the order above | The formats to take a model in, best first, separated by commas. A format left out is not taken - `stl,3mf` is meshes only - unless a part asks for it by its own `format` or `file`. |
| `source` | `auto` | Which of a model's files: `original` is what the designer uploaded, which takes a signed-in account; `preview` is the mesh MakerWorld's viewer shows of a print profile, coarser and needing no account; `auto` is the best original when there is a token, else a preview. |
| `token` | empty | The `token` cookie of makerworld.com, signed in with a Bambu Lab account. Only the designer's own files need it. `MAKERWORLD_TOKEN` gives it too. |

They are yours to set without touching this package - every one of them, the
credentials included, and the OAuth or API-key settings beside them:

- in your own `~/.partcad/config.yaml`, by the plugin's name, which is where
  `pc login` keeps the credentials:

  ```yaml
  parameters:
    "//pub/collection/makerworld:makerworld_repo":
      formats: stl,3mf
  ```

- or, for anything but the credentials, in a package of your own, as an enrich
  of the plugin and a package it serves - `//makerworld_meshes:<model>` in a
  package at the root:

  ```yaml
  repositories:
    meshes_repo:
      type: enrich
      source: //pub/collection/makerworld:makerworld_repo
      with:
        formats: stl,3mf
  dependencies:
    makerworld_meshes:
      type: external
      plugin: :meshes_repo
  ```

A part's own `file`, `format` and `source` override them for that part - in its
name (`1400000;format=stl`), or in the `with` of an enrich of the part:

```yaml
parts:
  clip:
    type: enrich
    source: //pub/collection/makerworld/models:1400000
    with:
      format: stl
```

PartCAD keys what it caches of this package on your overrides of the plugin's
parameters, so a change to one - logging in, too - takes effect at once. An
environment variable is not seen there: after setting one, `pc update`
refreshes what was cached without it.

## Logging in with nobody at the screen

An AI agent, or a script, logs in without a browser:

```shell
pc login --agent //pub/collection/makerworld:makerworld_repo
pc login --agent --set token=... //pub/collection/makerworld:makerworld_repo
```

The first prints what a person would do in the browser instead of opening one -
where to sign in, what to copy, and the command that hands it over - and exits
with status 3. It says that every print profile's preview can be had without a token (`source=preview`), and where in a signed-in browser the token is. The second hands over what the person found; the
plugin checks it with MakerWorld before PartCAD keeps it. `pc mcp`'s `login`
tool works the same way.

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
| `partcad.yaml` | `//pub/collection/makerworld`; the `models` external dependency and the `makerworld_repo` repository that serves it. |
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
