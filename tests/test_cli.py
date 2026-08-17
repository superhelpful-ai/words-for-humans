"""End-to-end checks of the command-line entry point."""

import json

import pytest

from words_for_humans import cli


@pytest.fixture()
def two_repos(tmp_path):
    """Two sibling directories, each with one scannable file."""
    target = tmp_path / "target"
    target.mkdir()
    (target / "README.md").write_text("One short line.\n")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "README.md").write_text("Another short line.\n")
    (elsewhere / "NOTES.md").write_text("A second file.\n")
    return target, elsewhere


def _run_json(argv, capsys):
    exit_code = cli.main(argv)
    assert exit_code == 0
    return json.loads(capsys.readouterr().out)


def test_root_flag_scans_the_root_not_the_cwd(two_repos, monkeypatch, capsys):
    target, elsewhere = two_repos
    monkeypatch.chdir(elsewhere)
    result = _run_json(
        ["-C", str(target), "--no-fail", "--no-baseline", "--format", "json"], capsys
    )
    assert result["files_scanned"] == 1


def test_no_arguments_scans_the_cwd(two_repos, monkeypatch, capsys):
    _, elsewhere = two_repos
    monkeypatch.chdir(elsewhere)
    result = _run_json(["--no-fail", "--no-baseline", "--format", "json"], capsys)
    assert result["files_scanned"] == 2


def test_explicit_paths_win_over_the_root(two_repos, monkeypatch, capsys):
    target, elsewhere = two_repos
    monkeypatch.chdir(elsewhere)
    result = _run_json(
        [str(elsewhere), "-C", str(target), "--no-fail", "--no-baseline", "--format", "json"],
        capsys,
    )
    assert result["files_scanned"] == 2


def test_install_skill_writes_the_packaged_skill(tmp_path, capsys):
    exit_code = cli.main(["-C", str(tmp_path), "--install-skill"])
    assert exit_code == 0
    written = tmp_path / ".claude" / "skills" / "words-for-humans-review" / "SKILL.md"
    assert written.is_file()
    assert written.read_text().startswith("---\nname: words-for-humans-review")


def test_install_skill_reports_an_unchanged_copy(tmp_path, capsys):
    assert cli.main(["-C", str(tmp_path), "--install-skill"]) == 0
    capsys.readouterr()
    assert cli.main(["-C", str(tmp_path), "--install-skill"]) == 0
    assert "already current" in capsys.readouterr().out


def test_the_summary_names_the_profile(two_repos, monkeypatch, capsys):
    _, elsewhere = two_repos
    monkeypatch.chdir(elsewhere)
    cli.main(["--no-fail", "--no-baseline"])
    out = capsys.readouterr().out
    assert "Profile code: Fails on comments that say nothing." in out


def test_the_summary_names_the_path_mappings(two_repos, monkeypatch, capsys):
    _, elsewhere = two_repos
    (elsewhere / ".words-for-humans.toml").write_text('[paths]\n"docs/**" = "prose-corporate"\n')
    monkeypatch.chdir(elsewhere)
    cli.main(["--no-fail", "--no-baseline"])
    out = capsys.readouterr().out
    assert "The [paths] table holds some files to prose-corporate." in out


def test_a_pr_description_is_checked_from_a_file(two_repos, monkeypatch, capsys, tmp_path):
    _, elsewhere = two_repos
    body = tmp_path / "body.md"
    body.write_text("It's worth noting that this pull request updates the parser.\n")
    monkeypatch.chdir(elsewhere)
    exit_code = cli.main(["--no-baseline", "--stdout", "--pr-description-file", str(body)])
    out = capsys.readouterr().out
    assert exit_code == 1
    assert "pull request description" in out
    assert "V-2" in out


def test_a_missing_description_file_is_a_usage_error(two_repos, monkeypatch, capsys):
    _, elsewhere = two_repos
    monkeypatch.chdir(elsewhere)
    exit_code = cli.main(["--pr-description-file", "no-such-file.md"])
    assert exit_code == 2
