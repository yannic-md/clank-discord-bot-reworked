"""Public API of the `modals` package.

Re-exporting every modal here lets callers do a single flat import from `modals` instead of having
to know which submodule each modal actually lives in (see the embed-builder's `modals/__init__.py`).

`__all__` declares this module's public API: it's the list `from ...modals import *`
would bind, and static analysis tools (mypy, IDEs) use it to know these names are
intentionally re-exported here, not just unused imports.
"""

from features.misc.builder.container.modals.content import ContainerModal, SeparatorModal, TextDisplayModal
from features.misc.builder.container.modals.media import MediaGalleryItemModal, ThumbnailModal
from features.misc.builder.container.modals.templates import SaveTemplateModal
from features.misc.builder.container.modals.webhook import ChannelModal, WebhookModal

__all__ = [
    "ChannelModal",
    "ContainerModal",
    "MediaGalleryItemModal",
    "SaveTemplateModal",
    "SeparatorModal",
    "TextDisplayModal",
    "ThumbnailModal",
    "WebhookModal",
]
