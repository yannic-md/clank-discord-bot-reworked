"""Public API of the `views` package.

Re-exporting every screen here lets callers do a single flat import from `views` instead of having
to know which submodule each view actually lives in (see the embed-builder's `views/__init__.py`).

`__all__` declares this module's public API: it's the list `from ...views import *`
would bind, and static analysis tools (mypy, IDEs) use it to know these names are
intentionally re-exported here, not just unused imports.
"""

from features.misc.builder.container.views.base import BuilderLayoutView, show, track_active_view
from features.misc.builder.container.views.component_list import ComponentKindListView
from features.misc.builder.container.views.gallery import MediaGalleryItemsView
from features.misc.builder.container.views.gui import MainView, MessageContentView
from features.misc.builder.container.views.move import MoveView
from features.misc.builder.container.views.order import ComponentOrderView
from features.misc.builder.container.views.send import SendConfirmView, save_message_changes
from features.misc.builder.container.views.templates import TemplatesView
from features.misc.builder.container.views.webhook import WebhookView

__all__ = [
    "BuilderLayoutView",
    "ComponentKindListView",
    "ComponentOrderView",
    "MainView",
    "MediaGalleryItemsView",
    "MessageContentView",
    "MoveView",
    "SendConfirmView",
    "TemplatesView",
    "WebhookView",
    "save_message_changes",
    "show",
    "track_active_view",
]
