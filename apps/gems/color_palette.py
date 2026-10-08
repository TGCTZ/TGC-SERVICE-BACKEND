"""Canonical identification colors and their synchronization logic."""

from apps.gems.enums import ColorGroup
from apps.gems.models import Color

COLORS = (
    ("Colorless", ColorGroup.WHITE_GREY_BLACK),
    ("Black", ColorGroup.WHITE_GREY_BLACK),
    ("Grey", ColorGroup.WHITE_GREY_BLACK),
    ("Violet", ColorGroup.PURPLE_VIOLET),
    ("Bluish violet", ColorGroup.PURPLE_VIOLET),
    ("Purple", ColorGroup.PURPLE_VIOLET),
    ("Bluish purple", ColorGroup.PURPLE_VIOLET),
    ("Reddish purple", ColorGroup.PURPLE_VIOLET),
    ("Orangy red", ColorGroup.RED_PINK),
    ("Red", ColorGroup.RED_PINK),
    ("Slightly purplish red", ColorGroup.RED_PINK),
    ("Strongly purplish red", ColorGroup.RED_PINK),
    ("Purple red or red purple", ColorGroup.RED_PINK),
    ("Pink", ColorGroup.RED_PINK),
    ("Greenish yellow", ColorGroup.ORANGE_YELLOW),
    ("Yellow", ColorGroup.ORANGE_YELLOW),
    ("Orange yellow", ColorGroup.ORANGE_YELLOW),
    ("Yellowish orange", ColorGroup.ORANGE_YELLOW),
    ("Orange", ColorGroup.ORANGE_YELLOW),
    ("Reddish orange", ColorGroup.ORANGE_YELLOW),
    ("Red orange or orange red", ColorGroup.ORANGE_YELLOW),
    ("Strongly bluish green", ColorGroup.GREEN),
    ("Slightly bluish green", ColorGroup.GREEN),
    ("Very slightly bluish green", ColorGroup.GREEN),
    ("Green", ColorGroup.GREEN),
    ("Slightly yellowish green", ColorGroup.GREEN),
    ("Yellowish green", ColorGroup.GREEN),
    ("Strongly yellowish green", ColorGroup.GREEN),
    ("Yellow green or green yellow", ColorGroup.GREEN),
    ("Violetish blue", ColorGroup.BLUE),
    ("Blue", ColorGroup.BLUE),
    ("Very slightly greenish blue", ColorGroup.BLUE),
    ("Greenish blue", ColorGroup.BLUE),
    ("Very strongly greenish blue", ColorGroup.BLUE),
    ("Green blue or blue green", ColorGroup.BLUE),
    ("Brown", ColorGroup.BROWN),
)


def sync_color_palette():
    """Make active color rows match the canonical palette and groups."""
    names = [name for name, _ in COLORS]

    for name, group in COLORS:
        color = Color.objects.filter(name=name).first()
        if color is None:
            color = (
                Color.all_objects.filter(name=name)
                .order_by("-deleted_at", "-pk")
                .first()
            )
            if color is not None:
                color.restore()
            else:
                color = Color(name=name, group=group)

        changed_fields = []
        if color.group != group:
            color.group = group
            changed_fields.append("group")
        if not color.is_active:
            color.is_active = True
            changed_fields.append("is_active")
        if changed_fields:
            color.save(update_fields=changed_fields)
        elif color.pk is None:
            color.save()

    Color.objects.exclude(name__in=names).delete()
