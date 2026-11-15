from discord import Interaction, SelectOption

from features.misc.builder.interactive.editor import describe_question, draft_name
from features.misc.builder.interactive.messages import screen
from features.misc.builder.interactive.modals import AfterQuestion, QuestionModal
from features.misc.builder.interactive.models import MAX_QUESTIONS_PER_FORM
from features.misc.builder.interactive.screens.common import bullet, clamp, list_body, swap, switch_dropdown
from features.misc.builder.interactive.screens.controls import (
    add_button,
    back_button,
    delete_button,
    down_button,
    edit_button,
    up_button,
)
from features.misc.builder.interactive.screens.host import Host
from features.misc.builder.interactive.screens.spec import Screen


def questions_screen(host: Host, item_id: int, *, active_index: int | None = None, error: str | None = None) -> Screen:
    """Lists the questions of one form and lets the user add, change, delete and reorder them.

    `item_id` is the form and `active_index` the selected question."""
    language = host.session.language

    draft = host.session.library.get(item_id)
    assert draft is not None
    questions = draft.questions
    active = clamp(active_index, len(questions))

    entries = [
        f"{bullet(number == active)} {describe_question(language, number + 1, question)}"
        for number, question in enumerate(questions)
    ]
    page = Screen(
        screen(language, "questions.title", name=draft_name(language, draft)),
        list_body(screen(language, "questions.description"), screen(language, "questions.list"), entries),
    )

    def after_question() -> AfterQuestion:
        """Build the callback that returns to this list after a question was added or changed."""

        async def after(interaction: Interaction, index: int | None, problem: str | None) -> None:
            """Show the question list again with the changed question selected."""
            await host.questions(interaction, item_id, active_index=index, error=problem)

        return after

    async def on_back(interaction: Interaction) -> None:
        """Go back to the form."""
        await host.form(interaction, item_id)

    async def on_add(interaction: Interaction) -> None:
        """Open the modal to add a question."""
        await interaction.response.send_modal(QuestionModal(language, draft, None, after_question()))

    async def on_edit(interaction: Interaction) -> None:
        """Open the modal to change the selected question."""
        assert active is not None
        await interaction.response.send_modal(QuestionModal(language, draft, active, after_question()))

    async def on_delete(interaction: Interaction) -> None:
        """Delete the selected question."""
        assert active is not None
        del questions[active]
        await host.questions(interaction, item_id, active_index=active)

    async def on_up(interaction: Interaction) -> None:
        """Move the selected question one position up."""
        assert active is not None and active > 0
        swap(questions, active, -1)
        await host.questions(interaction, item_id, active_index=active - 1)

    async def on_down(interaction: Interaction) -> None:
        """Move the selected question one position down."""
        assert active is not None and active < len(questions) - 1
        swap(questions, active, 1)
        await host.questions(interaction, item_id, active_index=active + 1)

    async def on_switch(interaction: Interaction, value: str) -> None:
        """Select another question."""
        await host.questions(interaction, item_id, active_index=int(value))

    page.add(0, back_button(language, on_back))
    page.add(
        0, add_button(screen(language, "buttons.question_add"), on_add, disabled=len(questions) >= MAX_QUESTIONS_PER_FORM)
    )
    page.add(0, edit_button(language, on_edit, disabled=active is None))
    page.add(0, delete_button(language, on_delete, disabled=active is None))
    page.add(1, up_button(language, on_up, disabled=active is None or active <= 0))
    page.add(1, down_button(language, on_down, disabled=active is None or active >= len(questions) - 1))

    switch_options = [
        SelectOption(label=f"{number + 1}. {question.label}"[:100], value=str(number), default=number == active)
        for number, question in enumerate(questions)
    ]
    page.add(
        2,
        switch_dropdown(
            switch_options,
            screen(language, "placeholders.switch_question" if questions else "placeholders.no_questions"),
            on_switch,
        ),
    )
    page.error = error
    return page
