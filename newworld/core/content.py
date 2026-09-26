"""Загрузка и проверка сюжетного контента.

Сцены лежат в YAML, а не в коде: сюжет пишется и правится без программиста.
Загрузчик строго проверяет файл при старте — опечатка в ссылке на сцену
должна падать сразу и с понятным текстом, а не через неделю у игрока.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from pathlib import Path
from typing import Any

import yaml

from .models import DEFAULT_ABILITIES, Ability, Gender


def normalize_prose(text: str) -> str:
    """Склеить строки абзаца в одну, сохранив разбиение на абзацы.

    В сюжетном файле текст удобно набирать в несколько коротких строк, но
    экран телефона узкий и переносит текст сам. Если оставить авторские
    переносы, они наложатся на экранные и абзац порвётся в случайных
    местах. Поэтому одиночный перенос — это пробел, а пустая строка —
    граница абзаца.
    """
    paragraphs = re.split(r"\n\s*\n", text.strip())
    return "\n\n".join(" ".join(p.split()) for p in paragraphs if p.strip())


class ContentError(ValueError):
    """Ошибка в сюжетном файле. Текст адресован автору контента."""


EFFECT_TYPES = {"damage", "heal", "gold", "item_gain", "item_lose", "flag"}


@dataclass(frozen=True)
class Effect:
    """Изменение состояния: урон, лечение, предмет, золото, флаг."""

    type: str
    amount: int = 0
    value: str = ""

    @classmethod
    def parse(cls, data: Any, where: str) -> Effect:
        if not isinstance(data, dict) or "type" not in data:
            raise ContentError(f"{where}: эффект должен быть словарём с ключом 'type', получено {data!r}")
        kind = data["type"]
        if kind not in EFFECT_TYPES:
            raise ContentError(
                f"{where}: неизвестный эффект {kind!r}. Доступны: {', '.join(sorted(EFFECT_TYPES))}"
            )
        if kind in ("damage", "heal", "gold"):
            if "amount" not in data:
                raise ContentError(f"{where}: эффекту {kind!r} нужен 'amount'")
            return cls(type=kind, amount=int(data["amount"]))
        if "value" not in data:
            raise ContentError(f"{where}: эффекту {kind!r} нужен 'value'")
        return cls(type=kind, value=str(data["value"]))


@dataclass(frozen=True)
class Requirement:
    """Условие, при котором вариант вообще показывается игроку."""

    flags: tuple[str, ...] = ()
    not_flags: tuple[str, ...] = ()
    items: tuple[str, ...] = ()
    min_gold: int = 0

    @classmethod
    def parse(cls, data: Any, where: str) -> Requirement:
        if data is None:
            return cls()
        if not isinstance(data, dict):
            raise ContentError(f"{where}: 'requires' должен быть словарём, получено {data!r}")
        unknown = set(data) - {"flags", "not_flags", "items", "min_gold"}
        if unknown:
            raise ContentError(f"{where}: неизвестные ключи в 'requires': {', '.join(sorted(unknown))}")
        return cls(
            flags=tuple(data.get("flags", [])),
            not_flags=tuple(data.get("not_flags", [])),
            items=tuple(data.get("items", [])),
            min_gold=int(data.get("min_gold", 0)),
        )

    @property
    def is_empty(self) -> bool:
        return not (self.flags or self.not_flags or self.items or self.min_gold)


@dataclass(frozen=True)
class Branch:
    """Одна ветка исхода: что сказать, что изменить, куда перейти."""

    text: str = ""
    effects: tuple[Effect, ...] = ()
    goto: str | None = None

    @classmethod
    def parse(cls, data: Any, where: str) -> Branch:
        if data is None:
            return cls()
        if not isinstance(data, dict):
            raise ContentError(f"{where}: ветка должна быть словарём, получено {data!r}")
        unknown = set(data) - {"text", "effects", "goto"}
        if unknown:
            raise ContentError(f"{where}: неизвестные ключи: {', '.join(sorted(unknown))}")
        effects = tuple(
            Effect.parse(e, f"{where}.effects[{i}]") for i, e in enumerate(data.get("effects", []) or [])
        )
        return cls(
            text=normalize_prose(str(data.get("text", ""))),
            effects=effects,
            goto=data.get("goto"),
        )


@dataclass(frozen=True)
class Check:
    """Проверка характеристики против сложности."""

    ability: Ability
    dc: int

    @classmethod
    def parse(cls, data: Any, where: str) -> Check:
        if not isinstance(data, dict):
            raise ContentError(f"{where}: 'check' должен быть словарём, получено {data!r}")
        if "ability" not in data or "dc" not in data:
            raise ContentError(f"{where}: 'check' требует 'ability' и 'dc'")
        try:
            ability = Ability(str(data["ability"]).lower())
        except ValueError:
            allowed = ", ".join(a.value for a in Ability)
            raise ContentError(f"{where}: неизвестная характеристика {data['ability']!r}. Доступны: {allowed}")
        return cls(ability=ability, dc=int(data["dc"]))


@dataclass(frozen=True)
class Option:
    """Вариант действия. Либо простой переход, либо проверка с двумя исходами."""

    id: str
    label: str
    requires: Requirement = Requirement()
    check: Check | None = None
    on_success: Branch = Branch()
    on_failure: Branch = Branch()
    # Для вариантов без проверки: единственная ветка.
    plain: Branch = Branch()

    @classmethod
    def parse(cls, data: Any, where: str) -> Option:
        if not isinstance(data, dict):
            raise ContentError(f"{where}: вариант должен быть словарём, получено {data!r}")
        for key in ("id", "label"):
            if key not in data:
                raise ContentError(f"{where}: варианту нужен {key!r}")
        unknown = set(data) - {
            "id", "label", "requires", "check", "on_success", "on_failure", "text", "effects", "goto"
        }
        if unknown:
            raise ContentError(f"{where}: неизвестные ключи: {', '.join(sorted(unknown))}")
        has_check = "check" in data
        if has_check and ("text" in data or "effects" in data or "goto" in data):
            raise ContentError(
                f"{where}: у варианта с 'check' исходы задаются в 'on_success'/'on_failure', "
                "а не напрямую в 'text'/'effects'/'goto'"
            )
        if not has_check and ("on_success" in data or "on_failure" in data):
            raise ContentError(f"{where}: 'on_success'/'on_failure' без 'check' не имеют смысла")
        return cls(
            id=str(data["id"]),
            label=str(data["label"]),
            requires=Requirement.parse(data.get("requires"), where),
            check=Check.parse(data["check"], where) if has_check else None,
            on_success=Branch.parse(data.get("on_success"), f"{where}.on_success"),
            on_failure=Branch.parse(data.get("on_failure"), f"{where}.on_failure"),
            plain=Branch.parse(
                {k: v for k, v in data.items() if k in ("text", "effects", "goto")} or None, where
            ),
        )


@dataclass(frozen=True)
class Scene:
    id: str
    title: str
    text: str
    options: tuple[Option, ...] = ()
    ending: bool = False

    @classmethod
    def parse(cls, data: Any, where: str) -> Scene:
        if not isinstance(data, dict):
            raise ContentError(f"{where}: сцена должна быть словарём, получено {data!r}")
        for key in ("id", "title", "text"):
            if key not in data:
                raise ContentError(f"{where}: сцене нужен {key!r}")
        unknown = set(data) - {"id", "title", "text", "options", "ending"}
        if unknown:
            raise ContentError(f"{where}: неизвестные ключи: {', '.join(sorted(unknown))}")
        options = tuple(
            Option.parse(o, f"сцена {data['id']!r}, вариант [{i}]")
            for i, o in enumerate(data.get("options", []) or [])
        )
        seen: set[str] = set()
        for option in options:
            if option.id in seen:
                raise ContentError(f"сцена {data['id']!r}: повторяющийся id варианта {option.id!r}")
            seen.add(option.id)
        ending = bool(data.get("ending", False))
        if not options and not ending:
            raise ContentError(
                f"сцена {data['id']!r}: нет вариантов и не помечена как 'ending: true' — "
                "игрок застрянет в тупике"
            )
        return cls(
            id=str(data["id"]),
            title=str(data["title"]),
            text=normalize_prose(str(data["text"])),
            options=options,
            ending=ending,
        )


@dataclass(frozen=True)
class Named:
    """Название в двух родах.

    В YAML пишется либо одной строкой (когда род не меняет слова), либо
    словарём ``{m: Травник, f: Травница}``.
    """

    male: str
    female: str

    def for_gender(self, gender: Gender) -> str:
        return self.male if gender is Gender.MALE else self.female

    @classmethod
    def parse(cls, data: Any, where: str) -> Named:
        if isinstance(data, str):
            return cls(male=data, female=data)
        if isinstance(data, dict):
            missing = {"m", "f"} - set(data)
            if missing:
                raise ContentError(
                    f"{where}: в названии не хватает {', '.join(sorted(missing))} "
                    "(нужны обе формы: {m: Травник, f: Травница})"
                )
            return cls(male=str(data["m"]), female=str(data["f"]))
        raise ContentError(f"{where}: название должно быть строкой или словарём, получено {data!r}")


def parse_abilities(
    data: Any, where: str, base: dict[Ability, int] | None
) -> dict[Ability, int]:
    """Разобрать набор характеристик.

    ``base`` — значения по умолчанию для неуказанных характеристик; None
    означает, что это прибавки, и указывать нужно только меняющиеся.
    """
    if not isinstance(data, dict):
        raise ContentError(f"{where}: характеристики должны быть словарём, получено {data!r}")
    result = dict(base) if base is not None else {}
    for key, value in data.items():
        try:
            ability = Ability(str(key).lower())
        except ValueError:
            allowed = ", ".join(a.value for a in Ability)
            raise ContentError(
                f"{where}: неизвестная характеристика {key!r}. Доступны: {allowed}"
            ) from None
        result[ability] = int(value)
    return result


@dataclass(frozen=True)
class Subclass:
    """Специализация. Её могут брать разные классы.

    Одна и та же выучка в руках разных людей — разное дело: следопыт из
    фронтовика читает след человека, следопыт из знахаря — след зверя и
    того, что зверем не является. Поэтому у специализации есть базовое
    описание и уточнения ``for_class``: они дополняют базу для
    конкретного класса и дают сочетанию собственный флаг.
    """

    id: str
    name: Named
    tagline: str
    description: str
    ability_bonus: dict[Ability, int] = field(default_factory=dict)
    hp_bonus: int = 0
    items: tuple[str, ...] = ()
    flags: tuple[str, ...] = ()
    # class_id -> чем эта специализация становится именно у него
    for_class: dict[str, "SubclassTwist"] = field(default_factory=dict)

    def resolved_for(self, class_id: str) -> Subclass:
        """Специализация в том виде, в каком её берёт этот класс."""
        twist = self.for_class.get(class_id)
        if twist is None:
            return self
        abilities = dict(self.ability_bonus)
        for ability, bonus in twist.ability_bonus.items():
            abilities[ability] = abilities.get(ability, 0) + bonus
        return Subclass(
            id=self.id,
            name=twist.name or self.name,
            tagline=twist.tagline or self.tagline,
            description=twist.description or self.description,
            ability_bonus=abilities,
            hp_bonus=self.hp_bonus + twist.hp_bonus,
            items=self.items + twist.items,
            flags=self.flags + twist.flags,
        )

    @classmethod
    def parse(cls, data: Any, where: str) -> Subclass:
        if not isinstance(data, dict):
            raise ContentError(f"{where}: специализация должна быть словарём, получено {data!r}")
        for key in ("id", "name", "tagline", "description"):
            if key not in data:
                raise ContentError(f"{where}: специализации нужен {key!r}")
        unknown = set(data) - {
            "id", "name", "tagline", "description",
            "ability_bonus", "hp_bonus", "items", "flags", "for_class",
        }
        if unknown:
            raise ContentError(f"{where}: неизвестные ключи: {', '.join(sorted(unknown))}")
        raw_twists = data.get("for_class") or {}
        if not isinstance(raw_twists, dict):
            raise ContentError(f"{where}: 'for_class' должен быть словарём «класс: уточнения»")
        twists = {
            str(class_id): SubclassTwist.parse(value, f"{where}, уточнение для {class_id!r}")
            for class_id, value in raw_twists.items()
        }
        return cls(
            id=str(data["id"]),
            name=Named.parse(data["name"], where),
            tagline=normalize_prose(str(data["tagline"])),
            description=normalize_prose(str(data["description"])),
            ability_bonus=parse_abilities(data.get("ability_bonus") or {}, where, base=None),
            hp_bonus=int(data.get("hp_bonus", 0)),
            items=tuple(str(i) for i in data.get("items", []) or []),
            flags=tuple(str(f) for f in data.get("flags", []) or []),
            for_class=twists,
        )


@dataclass(frozen=True)
class SubclassTwist:
    """Чем специализация становится в руках конкретного класса."""

    name: Named | None = None
    tagline: str = ""
    description: str = ""
    ability_bonus: dict[Ability, int] = field(default_factory=dict)
    hp_bonus: int = 0
    items: tuple[str, ...] = ()
    flags: tuple[str, ...] = ()

    @classmethod
    def parse(cls, data: Any, where: str) -> SubclassTwist:
        if not isinstance(data, dict):
            raise ContentError(f"{where}: уточнение должно быть словарём, получено {data!r}")
        unknown = set(data) - {
            "name", "tagline", "description", "ability_bonus", "hp_bonus", "items", "flags"
        }
        if unknown:
            raise ContentError(f"{where}: неизвестные ключи: {', '.join(sorted(unknown))}")
        return cls(
            name=Named.parse(data["name"], where) if "name" in data else None,
            tagline=normalize_prose(str(data.get("tagline", ""))),
            description=normalize_prose(str(data.get("description", ""))),
            ability_bonus=parse_abilities(data.get("ability_bonus") or {}, where, base=None),
            hp_bonus=int(data.get("hp_bonus", 0)),
            items=tuple(str(i) for i in data.get("items", []) or []),
            flags=tuple(str(f) for f in data.get("flags", []) or []),
        )


@dataclass(frozen=True)
class CharacterClass:
    """Кем игрок был до этой дороги: ремесло, судьба и взгляд на мир."""

    id: str
    name: Named
    tagline: str
    description: str
    abilities: dict[Ability, int]
    max_hp: int
    gold: int = 0
    items: tuple[str, ...] = ()
    flags: tuple[str, ...] = ()
    # Ссылки на общий список специализаций: одну и ту же может брать
    # несколько классов, и у каждого она своя.
    subclass_ids: tuple[str, ...] = ()

    @classmethod
    def parse(cls, data: Any, where: str) -> CharacterClass:
        if not isinstance(data, dict):
            raise ContentError(f"{where}: класс должен быть словарём, получено {data!r}")
        for key in ("id", "name", "tagline", "description", "abilities"):
            if key not in data:
                raise ContentError(f"{where}: классу нужен {key!r}")
        unknown = set(data) - {
            "id", "name", "tagline", "description", "abilities",
            "max_hp", "gold", "items", "flags", "subclasses",
        }
        if unknown:
            raise ContentError(f"{where}: неизвестные ключи: {', '.join(sorted(unknown))}")
        subclass_ids = tuple(str(i) for i in data.get("subclasses", []) or [])
        if len(set(subclass_ids)) != len(subclass_ids):
            raise ContentError(f"{where}: одна и та же специализация указана дважды")
        return cls(
            id=str(data["id"]),
            name=Named.parse(data["name"], where),
            tagline=normalize_prose(str(data["tagline"])),
            description=normalize_prose(str(data["description"])),
            abilities=parse_abilities(data["abilities"], where, base=DEFAULT_ABILITIES),
            max_hp=int(data.get("max_hp", 10)),
            gold=int(data.get("gold", 0)),
            items=tuple(str(i) for i in data.get("items", []) or []),
            flags=tuple(str(f) for f in data.get("flags", []) or []),
            subclass_ids=subclass_ids,
        )


@dataclass
class Story:
    """Весь сюжет: сцены плюс точка входа."""

    start_scene: str
    scenes: dict[str, Scene] = field(default_factory=dict)
    classes: tuple[CharacterClass, ...] = ()
    subclasses: dict[str, Subclass] = field(default_factory=dict)
    world_title: str = ""
    world_intro: str = ""

    def character_class(self, class_id: str) -> CharacterClass:
        for item in self.classes:
            if item.id == class_id:
                return item
        raise ContentError(f"Класс {class_id!r} не найден")

    def subclasses_of(self, character_class: CharacterClass) -> tuple[Subclass, ...]:
        """Специализации класса — уже с учётом того, чем они у него становятся."""
        return tuple(
            self.subclasses[subclass_id].resolved_for(character_class.id)
            for subclass_id in character_class.subclass_ids
        )

    def subclass_of(self, character_class: CharacterClass, subclass_id: str) -> Subclass:
        if subclass_id not in character_class.subclass_ids:
            raise ContentError(
                f"Класс {character_class.id!r} не может взять специализацию {subclass_id!r}"
            )
        return self.subclasses[subclass_id].resolved_for(character_class.id)

    def scene(self, scene_id: str) -> Scene:
        try:
            return self.scenes[scene_id]
        except KeyError:
            raise ContentError(f"Сцена {scene_id!r} не найдена") from None

    @classmethod
    def load(cls, path: str | Path) -> Story:
        path = Path(path)
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise ContentError(f"{path}: файл не разбирается как YAML: {exc}") from exc
        if not isinstance(raw, dict):
            raise ContentError(f"{path}: ожидался словарь с ключами 'start' и 'scenes'")
        if "start" not in raw or "scenes" not in raw:
            raise ContentError(f"{path}: нужны ключи 'start' и 'scenes'")
        scenes: dict[str, Scene] = {}
        for i, item in enumerate(raw["scenes"] or []):
            scene = Scene.parse(item, f"{path}: scenes[{i}]")
            if scene.id in scenes:
                raise ContentError(f"{path}: сцена {scene.id!r} объявлена дважды")
            scenes[scene.id] = scene
        subclasses: dict[str, Subclass] = {}
        for i, item in enumerate(raw.get("subclasses", []) or []):
            subclass = Subclass.parse(item, f"{path}: subclasses[{i}]")
            if subclass.id in subclasses:
                raise ContentError(f"{path}: специализация {subclass.id!r} объявлена дважды")
            subclasses[subclass.id] = subclass
        classes = tuple(
            CharacterClass.parse(item, f"{path}: classes[{i}]")
            for i, item in enumerate(raw.get("classes", []) or [])
        )
        seen_ids: set[str] = set()
        for character_class in classes:
            if character_class.id in seen_ids:
                raise ContentError(f"{path}: класс {character_class.id!r} объявлен дважды")
            seen_ids.add(character_class.id)
        world = raw.get("world") or {}
        if not isinstance(world, dict):
            raise ContentError(f"{path}: 'world' должен быть словарём с 'title' и 'intro'")
        story = cls(
            start_scene=str(raw["start"]),
            scenes=scenes,
            classes=classes,
            subclasses=subclasses,
            world_title=str(world.get("title", "")),
            world_intro=normalize_prose(str(world.get("intro", ""))),
        )
        story.validate()
        return story

    def validate(self) -> None:
        """Проверить, что все переходы ведут в существующие сцены."""
        if self.start_scene not in self.scenes:
            raise ContentError(f"Стартовая сцена {self.start_scene!r} не найдена")
        for character_class in self.classes:
            for subclass_id in character_class.subclass_ids:
                if subclass_id not in self.subclasses:
                    known = ", ".join(sorted(self.subclasses)) or "ни одной не объявлено"
                    raise ContentError(
                        f"класс {character_class.id!r}: специализация {subclass_id!r} "
                        f"не объявлена. Доступны: {known}"
                    )
        for subclass in self.subclasses.values():
            for class_id in subclass.for_class:
                if all(c.id != class_id for c in self.classes):
                    raise ContentError(
                        f"специализация {subclass.id!r}: уточнение для неизвестного "
                        f"класса {class_id!r}"
                    )
        for scene in self.scenes.values():
            for option in scene.options:
                branches = (
                    [option.plain] if option.check is None else [option.on_success, option.on_failure]
                )
                for branch in branches:
                    if branch.goto is not None and branch.goto not in self.scenes:
                        raise ContentError(
                            f"сцена {scene.id!r}, вариант {option.id!r}: "
                            f"переход в несуществующую сцену {branch.goto!r}"
                        )
