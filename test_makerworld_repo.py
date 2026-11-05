#
# partcad-makerworld, 2026
#
# Licensed under Apache License, Version 2.0.
#
"""Tests of the MakerWorld plugin, with MakerWorld answered from a table.

The design below has the shape design-service/design/<id> answers with - the
fields this reads, and some it does not - with values made up. Nothing here
touches the network.
"""

import base64
import importlib.util
import io
import json
import os
import runpy
import zipfile

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_PLUGIN = os.path.join(_HERE, "makerworld_repo.py")
_SPEC = importlib.util.spec_from_file_location("makerworld_repo_under_test", _PLUGIN)
plugin = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(plugin)
rm = plugin.rm

API = "https://makerworld.com/api/v1"
PREVIEW = "https://makerworld.bblmw.com/makerworld/model/X/1/instance/low_compression_glb/a.zip?exp=1"


def _instance(instance_id, title, preview=PREVIEW):
    return {
        "id": instance_id,
        "profileId": 1,
        "title": title,
        "extention": {
            "modelInfo": {"plates": []},
            "extensionModelFileList": [{"compressType": "low_compression_glb", "modelFile": preview}],
        },
    }


DESIGN = {
    "id": 1400000,
    "title": "Cable clip",
    "slug": "cable-clip",
    "license": "BY-NC-SA",
    "designCreator": {"uid": 1, "name": "Ann", "handle": "ann"},
    "instances": [_instance(1451665, "0.2mm layer, 2 walls"), _instance(1451666, "PETG")],
    "designExtension": {
        "model_files": [
            {"modelName": "clip.stl", "modelType": "stl", "modelSize": 1000, "modelUrl": "", "isDir": False},
            {"modelName": "clip.step", "modelType": "step", "modelSize": 2000, "modelUrl": "", "isDir": False},
            {
                "isDir": True,
                "dirName": "extras",
                "modelName": "",
                "children": [{"modelName": "base.3mf", "modelType": "3mf", "modelUrl": "", "isDir": False}],
            },
        ]
    },
}


def _zip(members):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        for name, data in members.items():
            z.writestr(name, data)
    return buffer.getvalue()


class Wire:
    def __init__(self, table):
        self.table = table
        self.asked = []

    def __call__(self, url, headers=None, data=None, method=None, timeout=60):
        self.asked.append((url, dict(headers or {})))
        if url not in self.table:
            return rm.Response(404, {}, b'{"code":404}', url)
        status, body = self.table[url]
        if not isinstance(body, bytes):
            body = json.dumps(body).encode()
        return rm.Response(status, {}, body, url)


@pytest.fixture
def site(tmp_path, monkeypatch):
    monkeypatch.setenv("PARTCAD_MAKERWORLD_CACHE", str(tmp_path))
    monkeypatch.delenv("MAKERWORLD_TOKEN", raising=False)

    def make(token=""):
        made = plugin.MakerWorld({"parameters": {"token": token}})
        made.http.request = Wire(
            {
                API + "/design-service/design/1400000": (200, DESIGN),
                PREVIEW: (200, _zip({"input_plate_1.glb": b"glTF-plate-1", "input_plate_2.glb": b"glTF-plate-2"})),
                API + "/design-service/design/1400000/model": (200, {"name": "x.zip", "url": "https://dl/x.zip"}),
                "https://dl/x.zip": (
                    200,
                    _zip({"clip.stl": b"solid", "clip.step": b"ISO-10303-21;", "extras/base.3mf": b"3mf"}),
                ),
            }
        )
        return made

    return make


def test_without_a_sign_in_a_model_is_its_preview_mesh(site):
    config = site().get("objects/part/1400000")
    assert config["type"] == "gltf"
    assert config["desc"] == "Cable clip: the preview mesh of the print profile '0.2mm layer, 2 walls'"
    assert config["parameters"]["file"]["default"] == "preview-1451665"
    assert config["url"] == "https://makerworld.com/en/models/1400000"
    assert config["author"] == "Ann"
    assert config["license"] == "CC BY-NC-SA 4.0"


def test_a_preview_is_the_first_plate_of_its_archive(site):
    made = site()
    config = made.get("objects/part/1400000;file=preview-1451666")
    assert base64.b64decode(made.get("files/" + config["path"])) == b"glTF-plate-1"


def test_with_a_sign_in_a_model_is_its_best_uploaded_file(site):
    config = site("secret").get("objects/part/1400000")
    assert config["type"] == "step" and config["desc"] == "Cable clip: clip.step"


def test_an_uploaded_file_is_taken_out_of_the_models_archive(site):
    made = site("secret")
    config = made.get("objects/part/1400000;file=extras/base.3mf")
    assert config["type"] == "3mf"
    assert base64.b64decode(made.get("files/" + config["path"])) == b"3mf"
    asked = [(url, headers.get("Authorization")) for url, headers in made.http.request.asked]
    assert (API + "/design-service/design/1400000/model", "Bearer secret") in asked
    assert ("https://dl/x.zip", None) in asked


def test_without_a_sign_in_an_uploaded_file_says_what_it_needs(site, capsys):
    made = site()
    config = made.get("objects/part/1400000;format=step")
    assert rm.serve(made, "files/" + config["path"]) is None
    err = capsys.readouterr().err
    assert "takes a signed-in MakerWorld account" in err and "format=glb" in err


def test_a_search_names_what_can_be_had(site):
    made = site()
    made.http.request.table[API + "/search-service/select/design/nav?keyword=clip&limit=60&offset=0"] = (
        200,
        {"total": 1, "hits": [{"id": 1400000, "title": "Cable clip", "designCreator": {"name": "Ann"}}]},
    )
    hits = made.get("search/part?q=clip")
    assert list(hits) == ["1400000;file=preview-1451665", "1400000;file=preview-1451666"]


def test_a_search_with_a_sign_in_names_the_uploaded_files(site):
    made = site("secret")
    made.http.request.table[API + "/search-service/select/design/nav?keyword=clip&limit=60&offset=0"] = (
        200,
        {"data": {"list": [{"id": 1400000, "title": "Cable clip"}]}},
    )
    assert list(made.get("search/part?q=clip")) == ["1400000;file=clip.step", "1400000;file=extras/base.3mf"]


def test_a_bot_check_on_the_search_is_reported(site, capsys):
    made = site()
    made.http.request.table[API + "/search-service/select/design/nav?keyword=clip&limit=60&offset=0"] = (
        403,
        b"<title>Just a moment...</title>",
    )
    assert rm.serve(made, "search/part?q=clip") is None
    assert "turned away by a Cloudflare bot check" in capsys.readouterr().err


def test_partcad_runs_it_and_reads_the_answer_from_output():
    result = runpy.run_path(_PLUGIN, init_globals={"request": {"key": "meta", "parameters": {}}}, run_name="get")
    assert result["output"]["result"]["manufacturable"] is False


def test_the_shared_module_is_the_one_every_model_site_plugin_has():
    import hashlib

    with open(os.path.join(_HERE, "remote_models.py"), "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    with open(os.path.join(_HERE, "remote_models.sha256")) as f:
        assert digest == f.read().split()[0], "remote_models.py differs from the shared copy: update all five"


# --- logging in ----------------------------------------------------------------

PROFILE = "https://api.bambulab.com/v1/user-service/my/profile"


def test_a_token_is_checked_by_asking_bambu_lab_who_it_is(site):
    made = site()
    made.http.request.table[PROFILE] = (200, {"uid": 1, "name": "Ann", "handle": "ann"})
    assert made.whoami({"token": "a.b.c"}) == "Ann"
    assert made.http.request.asked[-1] == (PROFILE, {"Authorization": "Bearer a.b.c"})
    made.http.request.table[PROFILE] = (401, {"code": 1, "error": "token expired"})
    assert made.whoami({"token": "a.b.c"}) is None


def test_the_login_takes_the_token_cookie_and_only_a_jwt(site):
    spec = site().login_spec()
    capture = spec["capture"][0]
    assert capture["cookie"] == {"url": "https://makerworld.com/", "name": "token"}
    import re

    assert re.match(capture["match"], "eyJhbGciOi.eyJzdWIiOi.c2lnbmF0dXJl")
    assert not re.match(capture["match"], "visitor-123")
