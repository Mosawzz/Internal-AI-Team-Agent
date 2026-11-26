
from app.ai.handoff import (
    generate_handoff_draft,
    render_handoff_draft,
)
from app.services.handoff_service import get_handoffs, save_handoff
from app.services.updates_service import get_task_history


def test_handoff_flow_is_traceable_to_source_updates(test_db):
    draft = generate_handoff_draft(test_db["task_id"])
    edited_content = (
        render_handoff_draft(draft)
        + "\nApproved after review."
    )

    saved = save_handoff(
        task_id=test_db["task_id"],
        author_id=test_db["user_id"],
        content=edited_content,
        source_update_ids=[test_db["update_id"]],
    )

    handoffs = get_handoffs(test_db["task_id"])

    assert len(handoffs) == 1
    assert handoffs[0].id == saved.id
    assert handoffs[0].status == "approved"
    assert f"U-{test_db['update_id']}" in draft.source_ids

    history_ids = {
        update.id for update in get_task_history(test_db["task_id"])
    }

    assert set(handoffs[0].source_update_ids) <= history_ids
