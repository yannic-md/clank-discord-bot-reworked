"""Public API of the `views` package.

Without this file, `features.misc.builder.embed.views` would be an implicit namespace package: importing
a name directly from it (`from ...views import EmbedAuthorModal`) would fail, since
namespace packages don't expose their submodules' contents automatically. Re-exporting
every view here lets callers do a single flat import from `views` instead of having
to know which submodule each view actually lives in.

`__all__` declares this module's public API: it's the list `from ...views import *`
would bind, and static analysis tools (mypy, IDEs) use it to know these names are
intentionally re-exported here, not just unused imports.
"""

from features.misc.builder.embed.views.base import show
from features.misc.builder.embed.views.embed_list import EmbedListView
from features.misc.builder.embed.views.fields import EmbedFieldsView
from features.misc.builder.embed.views.gui import EmbedBuilderGUI
from features.misc.builder.embed.views.send import SendConfirmView
from features.misc.builder.embed.views.templates import TemplatesView
from features.misc.builder.embed.views.webhook import WebhookView

__all__ = [
    "EmbedBuilderGUI",
    "EmbedFieldsView",
    "EmbedListView",
    "SendConfirmView",
    "TemplatesView",
    "WebhookView",
    "show",
]
