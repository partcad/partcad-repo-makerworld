#
# partcad-makerworld, 2026
#
# Licensed under Apache License, Version 2.0.
#
"""A PartCAD 'basic' repository plugin that serves MakerWorld models as parts.

Published as ``//pub/universe/makerworld/models``. Nothing is listed: a part is
asked for by the model's number (the one in makerworld.com/en/models/<number>),
and is one file of that model.

    1400000                          the model's best file (see remote_models.FORMATS)
    1400000;format=step              its best STEP
    1400000;file=bracket.stl         one of its files, by name
    1400000;source=preview           the preview mesh of its first print profile
    1400000;file=preview-1451665     the preview mesh of one of its print profiles

A model's details are MakerWorld's to give anyone, and so is the mesh its
viewer shows of each print profile - a '.glb' of the plate, served as a part in
its own right. The files the designer uploaded take a signed-in MakerWorld
account: give the plugin its token as MAKERWORLD_TOKEN, or as the repository's
'token' parameter (see the README). Without one, a model's best file is its
preview mesh - which the plugin's 'source' parameter can make it with one too.

PartCAD runs this script once per key (via runpy) with the key in
``request["key"]``; the answer goes in ``output``. What the keys mean, and
everything else that is the same for every model site, is in remote_models.py.
"""

import importlib.util
import io
import json
import os
import struct
import sys
import urllib.parse
import zipfile

# When this plugin's answers stopped meaning what they meant before. PartCAD
# keys everything it caches of this package on it, so raise it with any change
# to what is answered - here or in remote_models.py.
#
# v1: models as parts, one per uploaded file and one per print profile's preview; and 'login'.
# v2: a part's 'source' parameter, and the plugin's 'formats' and 'source' preferences;
#     'login' says what to do with nobody at the screen.
CACHE_VERSION = 2


def _shared():
    """remote_models.py, beside this script, under a name of this plugin's own."""
    name = "_partcad_makerworld_remote_models"
    if name not in sys.modules:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "remote_models.py")
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


rm = _shared()

WEB = "https://makerworld.com"
API = WEB + "/api/v1"

# A model's details carry signed links to its preview meshes, good for an hour.
# Kept for less than that, so a link read out of the cache still works.
_DESIGN_TTL = 30 * 60


def model_url(model_id):
    return "%s/en/models/%s" % (WEB, model_id)


def _license(value):
    """MakerWorld's 'BY-NC-SA' is Creative Commons' 'CC BY-NC-SA 4.0'."""
    if not isinstance(value, str) or not value:
        return None
    return "CC %s 4.0" % value if value.upper().startswith("BY") or value.upper() == "CC0" else value


def _raw_files(entries, prefix=""):
    """The files the designer uploaded, out of 'designExtension.model_files', folders flattened."""
    found = []
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        if entry.get("isDir"):
            folder = entry.get("dirName") or entry.get("modelName") or ""
            found += _raw_files(entry.get("children"), prefix + folder + "/" if folder else prefix)
            continue
        name = entry.get("modelName") or entry.get("modelFileName")
        if not name:
            continue
        found.append(
            rm.File(
                prefix + name,
                prefix + name,
                size=entry.get("modelSize"),
                raw=True,
                url=entry.get("modelUrl") or None,
            )
        )
    return found


def _preview_files(instances):
    """The mesh MakerWorld's viewer shows of each print profile, as a '.glb' each."""
    found = []
    for instance in instances or []:
        if not isinstance(instance, dict) or instance.get("id") is None:
            continue
        extension = instance.get("extention") or instance.get("extension") or {}
        for entry in extension.get("extensionModelFileList") or []:
            if "glb" in str(entry.get("compressType", "")).lower() and entry.get("modelFile"):
                found.append(
                    rm.File(
                        "preview-%s" % instance["id"],
                        "preview-%s.glb" % instance["id"],
                        fallback=True,
                        instance=instance["id"],
                        profile=instance.get("title"),
                    )
                )
                break
    return found


class MakerWorld(rm.Site):
    NAME = "makerworld"
    TITLE = "MakerWorld"
    URL = WEB
    DESC = "Models on MakerWorld, a part per file, by the model's number. Nothing is listed; search instead."
    VERSION = CACHE_VERSION
    PREVIEWS = True
    LOGIN_INSTRUCTIONS = (
        "Without logging in, every print profile's preview mesh can be had: ask for a part with 'source=preview', or "
        "leave 'source' at 'auto', which takes a preview when there is no token. The designer's own files take the "
        "'token' cookie of makerworld.com, from a browser signed in to MakerWorld with a Bambu Lab account: the "
        "browser's developer tools show it, under Application (or Storage) > Cookies."
    )

    def __init__(self, request=None):
        super().__init__(request)
        self.token = rm.credential(self.request, "token", "MAKERWORLD_TOKEN")

    def valid_id(self, model_id):
        return model_id.isdigit()

    CREDENTIALS = {"token": "MAKERWORLD_TOKEN"}

    # -- logging in --

    def whoami(self, credentials):
        token = credentials.get("token")
        if not token:
            return None
        # Bambu Lab's cloud API, which MakerWorld's sign-in is the sign-in of.
        # Asked there rather than on makerworld.com, whose own profile request
        # some networks get a bot check for.
        status, me = self.http.probe(
            "https://api.bambulab.com/v1/user-service/my/profile",
            "who the MakerWorld token is",
            headers={"Authorization": "Bearer " + token},
        )
        if status in (401, 403):
            return None
        if status != 200 or not isinstance(me, dict):
            raise rm.SiteError("makerworld: asking who the token is answered HTTP %d" % status)
        return me.get("name") or me.get("handle") or str(me.get("uid") or "") or "a MakerWorld user"

    def login_spec(self):
        # MakerWorld keeps a signed-in user's access token in a cookie named
        # 'token' - a JWT, which is what 'match' asks for, so nothing a visitor
        # has can be taken for it.
        return {
            "url": "https://makerworld.com/en",
            "title": "MakerWorld",
            "capture": [
                {
                    "name": "token",
                    "cookie": {"url": "https://makerworld.com/", "name": "token"},
                    "match": r"^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$",
                }
            ],
            "guide": [
                {
                    # A Material UI button, which nothing but its text tells
                    # apart from the others (seen on makerworld.com/en).
                    "url": "https://makerworld.com/*",
                    "selector": "button, a",
                    "contains": "^\\s*log ?in\\s*$",
                    "text": "Sign in with your Bambu Lab account",
                },
                {
                    "url": "https://bambulab.com/*",
                    "selector": "input[type=email], input[type=text]",
                    "text": "Sign in with your Bambu Lab account",
                },
            ],
        }

    def usable(self, file):
        # The designer's own files take a signed-in account; a preview does not.
        return bool(self.token) or not file.extra.get("raw")

    def _design(self, model_id, ttl=_DESIGN_TTL):
        design = self.http.json("%s/design-service/design/%s" % (API, model_id), "model %s" % model_id, ttl=ttl)
        if not isinstance(design, dict) or design.get("id") is None:
            raise rm.NotFound("makerworld: model %s: not found" % model_id)
        return design

    def model(self, model_id):
        design = self._design(model_id)
        return rm.Model(
            model_id,
            title=design.get("title"),
            url=model_url(model_id),
            author=(design.get("designCreator") or {}).get("name"),
            license=_license(design.get("license")),
            files=_raw_files((design.get("designExtension") or {}).get("model_files"))
            + _preview_files(design.get("instances")),
        )

    def part_config(self, model, file):
        config = super().part_config(model, file)
        if file.fallback:
            title = model.title or "MakerWorld model %s" % model.id
            config["desc"] = "%s: the preview mesh of the print profile '%s'" % (
                title,
                file.extra.get("profile") or file.extra.get("instance"),
            )
        return config

    def download(self, model, file):
        what = "%s of model %s" % (file.name, model.id)
        if file.fallback:
            # Read again rather than out of the cache: the link is signed, and
            # good for an hour.
            for instance in self._design(model.id, ttl=0).get("instances") or []:
                if isinstance(instance, dict) and instance.get("id") == file.extra.get("instance"):
                    extension = instance.get("extention") or instance.get("extension") or {}
                    for entry in extension.get("extensionModelFileList") or []:
                        if "glb" in str(entry.get("compressType", "")).lower() and entry.get("modelFile"):
                            return self._glb(self.http.download(entry["modelFile"], what), what)
            raise rm.NotFound("makerworld: model %s no longer has the print profile %s" % (model.id, file.id))
        if not self.token:
            raise rm.NeedsCredentials(
                "makerworld: %s takes a signed-in MakerWorld account: set MAKERWORLD_TOKEN, or the "
                "'token' parameter of the repository (see the README; 'pc login' sets it), or ask for "
                "'%s;source=preview', a print profile's preview mesh, which needs none" % (what, model.id)
            )
        auth = {"Authorization": "Bearer " + self.token}
        if file.extra.get("url"):
            data = self.http.download(file.extra["url"], what)
        else:
            try:
                answer = self.http.json(
                    "%s/design-service/design/%s/model" % (API, model.id),
                    "the files of model %s" % model.id,
                    headers=auth,
                    ttl=0,
                )
            except rm.NeedsCredentials as e:
                raise rm.NeedsCredentials(
                    "%s. The MakerWorld token in MAKERWORLD_TOKEN or the 'token' parameter was not accepted; "
                    "it may have expired" % e
                )
            link = answer.get("url") if isinstance(answer, dict) else None
            if not link:
                raise rm.SiteError(
                    "makerworld: the files of model %s were not handed over: %s"
                    % (model.id, (answer or {}).get("error") if isinstance(answer, dict) else answer)
                )
            data = self.http.download(link, "the files of model %s" % model.id)
        if rm.is_zip(data) and not file.name.lower().endswith(".zip"):
            member = rm.read_zip_member(data, file.name)
            if member is None:
                raise rm.NotFound("makerworld: the files of model %s do not include %s" % (model.id, file.name))
            return member
        return data

    @staticmethod
    def _glb(data, what):
        """The '.glb' a preview archive holds (the first plate's, when there are several), uncompressed."""
        if rm.is_zip(data):
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                meshes = sorted(n for n in z.namelist() if n.lower().endswith(".glb"))
                if not meshes:
                    raise rm.SiteError("makerworld: %s holds no mesh" % what)
                data = z.read(meshes[0])
        return undraco(data, what)

    def search(self, text, limit):
        # Best effort: this is what the site's own search page asks, and it is
        # not a documented API. A bot check answers it from some networks.
        answer = self.http.json(
            "%s/search-service/select/design/nav?%s"
            % (API, urllib.parse.urlencode({"keyword": text, "limit": limit, "offset": 0})),
            "a search for '%s'" % text,
            ttl=600,
        )
        models = []
        for hit in _hits(answer):
            model_id = str(hit.get("id"))
            creator = hit.get("designCreator") or hit.get("creator") or {}
            models.append(
                rm.Model(
                    model_id,
                    title=hit.get("title") or hit.get("name"),
                    url=model_url(model_id),
                    author=creator.get("name") if isinstance(creator, dict) else None,
                    license=_license(hit.get("license")),
                )
            )
        return models


# --- Draco ---------------------------------------------------------------------
#
# MakerWorld compresses its preview meshes with Draco (the glTF extension
# KHR_draco_mesh_compression, which it marks as required), and a glTF reader
# that does not decode Draco - PartCAD's does not - finds no triangles in one.
# So the plugin writes each such mesh out as the plain triangles it holds, and
# leaves the rest of the file - its nodes, so where each mesh is; its units;
# which way is up - for PartCAD's reader to read as it reads any '.glb'. What
# is dropped is what a preview has and a part does not need: normals, colours,
# textures.
#
# DracoPy is what decodes it; the package declares it in 'pythonRequirements',
# so it is in the sandbox this runs in.

_GLB_MAGIC = b"glTF"
_JSON_CHUNK = 0x4E4F534A
_BIN_CHUNK = 0x004E4942
_DRACO = "KHR_draco_mesh_compression"
_COMPONENTS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}
_DTYPES = {5120: "i1", 5121: "u1", 5122: "<i2", 5123: "<u2", 5125: "<u4", 5126: "<f4"}


def _chunks(glb):
    """(JSON document, binary chunk) of a '.glb'."""
    magic, _, length = struct.unpack_from("<4sII", glb, 0)
    if magic != _GLB_MAGIC:
        raise ValueError("not a binary glTF")
    offset, document, binary = 12, None, b""
    while offset + 8 <= min(length, len(glb)):
        size, kind = struct.unpack_from("<II", glb, offset)
        body = glb[offset + 8 : offset + 8 + size]
        if kind == _JSON_CHUNK:
            document = json.loads(body.decode("utf-8"))
        elif kind == _BIN_CHUNK:
            binary = body
        offset += 8 + size
    if document is None:
        raise ValueError("a binary glTF with no JSON in it")
    return document, binary


def _accessor(document, binary, index):
    """The values of an accessor of the binary chunk, as a numpy array of rows."""
    import numpy

    accessor = document["accessors"][index]
    view = document["bufferViews"][accessor["bufferView"]]
    width = _COMPONENTS[accessor["type"]]
    dtype = numpy.dtype(_DTYPES[accessor["componentType"]])
    start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    stride = view.get("byteStride") or width * dtype.itemsize
    rows = numpy.ndarray(
        (accessor["count"], width), dtype=dtype, buffer=binary, offset=start, strides=(stride, dtype.itemsize)
    )
    return numpy.array(rows)


def undraco(glb, what="a mesh"):
    """'glb' with every Draco-compressed mesh in it written out plainly; 'glb' itself if there is none."""
    try:
        document, binary = _chunks(glb)
    except (ValueError, struct.error):
        return glb
    if _DRACO not in (document.get("extensionsUsed") or []):
        return glb
    try:
        import DracoPy
        import numpy
    except ImportError as e:
        raise rm.SiteError(
            "makerworld: %s is Draco-compressed, and decoding it needs DracoPy in the sandbox (%s); "
            "the package declares it in 'pythonRequirements'" % (what, e)
        )

    out = bytearray()
    views, accessors = [], []

    def add(rows, component_type, kind, bounds=False):
        while len(out) % 4:
            out.append(0)
        data = rows.tobytes()
        views.append({"buffer": 0, "byteOffset": len(out), "byteLength": len(data)})
        out.extend(data)
        accessor = {
            "bufferView": len(views) - 1,
            "componentType": component_type,
            "count": int(rows.shape[0]),
            "type": kind,
        }
        if bounds and rows.shape[0]:
            accessor["min"] = [float(v) for v in rows.min(axis=0)]
            accessor["max"] = [float(v) for v in rows.max(axis=0)]
        accessors.append(accessor)
        return len(accessors) - 1

    meshes = []
    for mesh in document.get("meshes") or []:
        primitives = []
        for primitive in mesh.get("primitives") or []:
            draco = (primitive.get("extensions") or {}).get(_DRACO)
            if draco is not None:
                view = document["bufferViews"][draco["bufferView"]]
                start = view.get("byteOffset", 0)
                decoded = DracoPy.decode(bytes(binary[start : start + view["byteLength"]]))
                points = numpy.asarray(decoded.points, dtype=numpy.float32).reshape(-1, 3)
                faces = numpy.asarray(decoded.faces, dtype=numpy.uint32).reshape(-1, 1)
            elif "POSITION" in (primitive.get("attributes") or {}):
                points = _accessor(document, binary, primitive["attributes"]["POSITION"]).astype(numpy.float32)
                if primitive.get("indices") is not None:
                    faces = _accessor(document, binary, primitive["indices"]).astype(numpy.uint32).reshape(-1, 1)
                else:
                    faces = numpy.arange(points.shape[0], dtype=numpy.uint32).reshape(-1, 1)
            else:
                continue
            primitives.append(
                {
                    "attributes": {"POSITION": add(points, 5126, "VEC3", bounds=True)},
                    "indices": add(faces, 5125, "SCALAR"),
                    "mode": primitive.get("mode", 4),
                }
            )
        meshes.append({"primitives": primitives, **({"name": mesh["name"]} if "name" in mesh else {})})

    keep = ("name", "mesh", "children", "matrix", "translation", "rotation", "scale")
    plain = {
        "asset": {"version": "2.0", "generator": "partcad-makerworld"},
        "scenes": document.get("scenes") or [{"nodes": list(range(len(document.get("nodes") or [])))}],
        "nodes": [{k: v for k, v in node.items() if k in keep} for node in document.get("nodes") or []],
        "meshes": meshes,
        "buffers": [{"byteLength": len(out)}],
        "bufferViews": views,
        "accessors": accessors,
    }
    if "scene" in document:
        plain["scene"] = document["scene"]
    text = json.dumps(plain, separators=(",", ":")).encode("utf-8")
    text += b" " * (-len(text) % 4)
    while len(out) % 4:
        out.append(0)
    body = struct.pack("<II", len(text), _JSON_CHUNK) + text + struct.pack("<II", len(out), _BIN_CHUNK) + bytes(out)
    return struct.pack("<4sII", _GLB_MAGIC, 2, 12 + len(body)) + body


def _hits(answer, depth=0):
    """The models in a search answer, wherever in it they are."""
    if depth > 3:
        return []
    if isinstance(answer, list):
        found = [h for h in answer if isinstance(h, dict) and str(h.get("id", "")).isdigit() and h.get("title")]
        if found:
            return found
        return [h for item in answer for h in _hits(item, depth + 1)]
    if isinstance(answer, dict):
        for key in ("hits", "items", "designs", "list", "data", "result"):
            if key in answer:
                found = _hits(answer[key], depth + 1)
                if found:
                    return found
    return []


def get(key):
    return rm.serve(MakerWorld(globals().get("request")), key)


# Last, so that everything above is defined when PartCAD runs this.
if __name__ == "get":
    output = {"result": get(request["key"])}  # noqa: F821 - injected by the runtime
elif __name__ == "login":
    output = {"result": rm.login(MakerWorld(globals().get("request")), globals().get("partcad_login"))}
else:
    output = {}
