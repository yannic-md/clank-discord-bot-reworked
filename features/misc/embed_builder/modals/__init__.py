"""Public API of the `modals` package.

Without this file, `features.misc.embed_builder.modals` would be an implicit namespace package: importing
a name directly from it (`from ...modals import EmbedAuthorModal`) would fail, since
namespace packages don't expose their submodules' contents automatically. Re-exporting
every modal here lets callers do a single flat import from `modals` instead of having
to know which submodule each modal actually lives in.

`__all__` declares this module's public API: it's the list `from ...modals import *`
would bind, and static analysis tools (mypy, IDEs) use it to know these names are
intentionally re-exported here, not just unused imports.
"""

from features.misc.embed_builder.modals.content import EmbedColourModal, EmbedTitleDescModal, MessageContentModal
from features.misc.embed_builder.modals.fields import EmbedFieldModal
from features.misc.embed_builder.modals.media import (
    EmbedAuthorModal,
    EmbedFooterModal,
    EmbedImagesModal,
    EmbedTimestampModal,
)
from features.misc.embed_builder.modals.templates import SaveTemplateModal
from features.misc.embed_builder.modals.webhook import ChannelModal, WebhookModal, find_webhook

__all__ = [
    "ChannelModal",
    "EmbedAuthorModal",
    "EmbedColourModal",
    "EmbedFieldModal",
    "EmbedFooterModal",
    "EmbedImagesModal",
    "EmbedTimestampModal",
    "EmbedTitleDescModal",
    "MessageContentModal",
    "SaveTemplateModal",
    "WebhookModal",
    "find_webhook",
]
