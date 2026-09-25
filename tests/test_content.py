import textwrap

import pytest

from newworld.core.content import ContentError, Story


def write_story(tmp_path, body):
    path = tmp_path / "story.yaml"
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


MINIMAL = """
    start: a
    scenes:
      - id: a
        title: А
        text: Текст
        options:
          - id: go
            label: Дальше
            goto: b
      - id: b
        title: Б
        text: Конец
        ending: true
"""


def test_loads_valid_story(tmp_path):
    story = Story.load(write_story(tmp_path, MINIMAL))
    assert story.start_scene == "a"
    assert set(story.scenes) == {"a", "b"}


def test_rejects_dangling_goto(tmp_path):
    path = write_story(tmp_path, MINIMAL.replace("goto: b", "goto: nowhere"))
    with pytest.raises(ContentError, match="несуществующую сцену"):
        Story.load(path)


def test_rejects_missing_start_scene(tmp_path):
    path = write_story(tmp_path, MINIMAL.replace("start: a", "start: zzz"))
    with pytest.raises(ContentError, match="Стартовая сцена"):
        Story.load(path)


def test_rejects_dead_end_scene(tmp_path):
    path = write_story(tmp_path, MINIMAL.replace("        ending: true", ""))
    with pytest.raises(ContentError, match="тупик"):
        Story.load(path)


def test_rejects_duplicate_option_ids(tmp_path):
    path = write_story(
        tmp_path,
        """
        start: a
        scenes:
          - id: a
            title: А
            text: Т
            options:
              - id: go
                label: Раз
                goto: a
              - id: go
                label: Два
                goto: a
        """,
    )
    with pytest.raises(ContentError, match="повторяющийся id"):
        Story.load(path)


def test_rejects_unknown_effect(tmp_path):
    path = write_story(
        tmp_path,
        """
        start: a
        scenes:
          - id: a
            title: А
            text: Т
            options:
              - id: go
                label: Раз
                effects:
                  - type: телепортация
                    value: куда-то
        """,
    )
    with pytest.raises(ContentError, match="неизвестный эффект"):
        Story.load(path)


def test_rejects_check_branches_mixed_with_plain_result(tmp_path):
    path = write_story(
        tmp_path,
        """
        start: a
        scenes:
          - id: a
            title: А
            text: Т
            options:
              - id: go
                label: Раз
                check:
                  ability: wis
                  dc: 10
                goto: a
        """,
    )
    with pytest.raises(ContentError, match="on_success"):
        Story.load(path)


def test_demo_story_is_valid():
    """Демо-сюжет в репозитории всегда должен грузиться."""
    story = Story.load("content/olhovets.yaml")
    assert len(story.scenes) >= 5
    assert any(scene.ending for scene in story.scenes.values())
