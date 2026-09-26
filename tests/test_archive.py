"""Game files: Markdown out, the same game back in, and nothing unsafe loads."""

import base64
import pickle
import random
import zlib

import pytest
from test_editions import lobby, play

from botc_automod import archive


def game(edition="tb", seed=3, steps=6):
    rng = random.Random(seed)
    g = lobby(8, edition, seed, "auto")
    g.start()
    play(g, rng, steps)
    return g, rng


@pytest.mark.parametrize("edition", ["tb", "bmr", "snv"])
def test_round_trip_resumes_the_same_game(edition):
    g, rng = game(edition)
    back = archive.from_markdown(archive.to_markdown(g))
    assert back.code == g.code and back.phase == g.phase and back.day == g.day
    assert [(p.name, p.role, p.alive, p.token) for p in back.seated()] == \
           [(p.name, p.role, p.alive, p.token) for p in g.seated()]
    play(back, rng, 500)   # the copy plays on to the end
    assert back.phase == "ended"


def test_running_file_shows_no_secrets():
    g, _ = game()
    text = archive.to_markdown(g, paused=True)
    meta = archive.header(text)
    assert meta["status"] == "paused" and meta["code"] == g.code and meta["players"] == "8"
    readable = text.split("## Town log")[0]   # the town log may hold public claims
    for p in g.seated():
        assert g.edition.roles[p.role].name not in readable


def test_completed_file_shows_the_grimoire_and_notebooks():
    g, rng = game()
    play(g, rng, 500)
    text = archive.to_markdown(g)
    meta = archive.header(text)
    assert meta["status"] == "completed" and meta["winner"] == g.winner
    for p in g.seated():
        assert g.edition.roles[p.role].name in text
    assert "## Notebooks" in text


class Boom:
    def __reduce__(self):
        return (print, ("pwned",))


def test_a_file_with_other_objects_is_refused():
    blob = base64.b64encode(zlib.compress(pickle.dumps(Boom()))).decode()
    with pytest.raises(archive.ArchiveError, match="forbidden"):
        archive.from_markdown(f"# x\n\n```botc-save schema=2\n{blob}\n```\n")


@pytest.mark.parametrize("text", ["", "# Just notes", "```botc-save\nnot base64!\n```\n"])
def test_bad_files_give_a_clear_error(text):
    with pytest.raises(archive.ArchiveError):
        archive.from_markdown(text)


def test_listing_and_free_names(tmp_path):
    g, _ = game()
    d = archive.folder(tmp_path, "paused")
    a = archive.free_path(d, archive.file_name(g))
    archive.write(a, g, paused=True)
    b = archive.free_path(d, archive.file_name(g))
    assert b.name.endswith("-2.md")
    archive.write(b, g, paused=True)
    rows = archive.listing(tmp_path, "paused")
    assert len(rows) == 2 and rows[0]["code"] == g.code and rows[0]["host"] == g.host.name


@pytest.mark.parametrize("name", ["../x.md", "a/b.md", ".hidden.md", "x.txt", "x.md/.."])
def test_safe_name_blocks_paths(name):
    with pytest.raises(archive.ArchiveError):
        archive.safe_name(name)
