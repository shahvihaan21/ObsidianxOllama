"""Obsidian vault tests: search, read, create, append, and the path boundary."""

import pytest

from app.obsidian import (
    NOTE_EXISTS,
    NOTE_NOT_FOUND,
    NOT_CONFIGURED,
    OUTSIDE_VAULT,
    Obsidian,
    ObsidianError,
)


@pytest.fixture
def vault(tmp_path):
    return Obsidian(vault=str(tmp_path))


def test_create_read_append_and_search(vault, tmp_path):
    assert "Created" in vault.create("Project", "# Project Roadmap")
    assert (tmp_path / "Project.md").is_file()
    assert vault.read("Project") == "# Project Roadmap"

    assert "Appended" in vault.append("Project", "- Milestone 1")
    body = vault.read("Project.md")
    assert "# Project Roadmap" in body
    assert "- Milestone 1" in body

    hits = vault.search("milestone")
    assert [hit["note"] for hit in hits] == ["Project.md"]
    assert "Milestone 1" in hits[0]["snippet"]


def test_search_matches_filenames_and_contents(vault):
    vault.create("Portfolio Analysis", "nothing to see here")
    vault.create("Random", "this mentions portfolio analysis too")
    notes = {hit["note"] for hit in vault.search("portfolio analysis")}
    assert notes == {"Portfolio Analysis.md", "Random.md"}


def test_search_with_no_matches(vault):
    vault.create("Notes", "hello")
    assert vault.search("a term that is absent") == []


def test_duplicate_create_is_refused(vault):
    vault.create("Investment Ideas", "first version")
    with pytest.raises(ObsidianError) as excinfo:
        vault.create("Investment Ideas", "second version")
    assert str(excinfo.value) == NOTE_EXISTS
    assert vault.read("Investment Ideas") == "first version"


def test_read_missing_note(vault):
    with pytest.raises(ObsidianError) as excinfo:
        vault.read("Does Not Exist")
    assert str(excinfo.value) == NOTE_NOT_FOUND


def test_append_missing_note_is_refused(vault):
    with pytest.raises(ObsidianError) as excinfo:
        vault.append("Does Not Exist", "text")
    assert str(excinfo.value) == NOTE_NOT_FOUND
    assert not (vault.vault / "Does Not Exist.md").exists()


def test_markdown_extension_is_forced(vault, tmp_path):
    vault.create("Ideas.txt", "x")
    assert (tmp_path / "Ideas.md").is_file()
    assert not (tmp_path / "Ideas.txt").exists()


def test_nested_note_paths(vault, tmp_path):
    vault.create("Projects/2026/Investment Ideas", "nested")
    assert (tmp_path / "Projects" / "2026" / "Investment Ideas.md").is_file()
    assert vault.read("Projects/2026/Investment Ideas") == "nested"
    assert (
        vault.note_path_for("Projects/2026/Investment Ideas")
        == "Projects/2026/Investment Ideas.md"
    )


@pytest.mark.parametrize(
    "bad",
    [
        "../../test.txt",
        "..\\..\\test.txt",
        "../escape.md",
        "Notes/../../escape.md",
        "C:/Windows/System32/evil.md",
        "C:\\Windows\\System32\\evil.md",
        "\\\\server\\share\\evil.md",
    ],
)
def test_path_traversal_is_rejected(vault, bad):
    attempts = (
        lambda: vault.read(bad),
        lambda: vault.create(bad, "x"),
        lambda: vault.append(bad, "x"),
        lambda: vault.note_path_for(bad),
    )
    for attempt in attempts:
        with pytest.raises(ObsidianError) as excinfo:
            attempt()
        assert str(excinfo.value) == OUTSIDE_VAULT


def test_absolute_path_outside_vault_is_rejected(vault, tmp_path):
    outside = tmp_path.parent / "outside.md"
    with pytest.raises(ObsidianError) as excinfo:
        vault.create(str(outside), "x")
    assert str(excinfo.value) == OUTSIDE_VAULT
    assert not outside.exists()


def test_unconfigured_vault_reports_clearly():
    empty = Obsidian(vault="")
    assert not empty.configured
    attempts = (
        lambda: empty.search("x"),
        lambda: empty.read("x"),
        lambda: empty.create("x"),
        lambda: empty.list_notes(),
    )
    for attempt in attempts:
        with pytest.raises(ObsidianError) as excinfo:
            attempt()
        assert str(excinfo.value) == NOT_CONFIGURED


def test_list_notes(vault):
    vault.create("Zeta", "z")
    vault.create("Projects/Alpha", "a")
    assert vault.list_notes() == ["Projects/Alpha.md", "Zeta.md"]


def test_list_notes_on_an_empty_vault(vault):
    assert vault.list_notes() == []


def test_list_notes_respects_the_limit(vault):
    for index in range(5):
        vault.create(f"Note {index}", "x")
    assert len(vault.list_notes(limit=2)) == 2
