from pydantic import BaseModel, Field
import os
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from app.errors import ModelUnavailableError, ExtractionError
from pydantic import BaseModel, Field, ValidationError
from langchain_core.exceptions import OutputParserException

class ProgressUpdateDraft(BaseModel):
    completed_work: list[str] = Field(default_factory=list)
    remaining_work: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    next_step: str | None = None


PROGRESS_EXTRACTION_SYSTEM_PROMPT = """
You are a progress update extraction assistant
for an internal team project management system.

Your task is to extract structured progress information
from the user's natural language progress update.

Extract exactly these four fields:

1. completed_work:
   A list of tasks or activities the user explicitly
   states they have completed.

2. remaining_work:
   A list of tasks or activities the user explicitly
   states are not completed yet.

3. blockers:
   A list of problems, obstacles, or issues preventing
   the user from making progress.

4. next_step:
   A string describing the user's explicitly stated
   next action, or null if no next action is mentioned.

IMPORTANT RULES:

- Only extract information explicitly mentioned by the user.
- Never invent, assume, or guess missing information.
- Do not interpret planned work as completed work.
- Do not interpret completed work as remaining work.
- If a field has no supported information, return an empty
  list for list fields and null for next_step.
- Do not use placeholders such as "N/A" or "Unknown".
- Preserve the original meaning of the user's statements.
- Keep extracted items concise and clear.
- Return data matching the ProgressUpdateDraft schema.
- Do not include explanations outside the structured output.
"""


def extract_progress_draft(
    task_id: int,
    free_text: str
) -> ProgressUpdateDraft:

    if not isinstance(task_id, int) or isinstance(task_id, bool) or task_id <= 0:
        raise ExtractionError("Invalid task ID.")

    if not isinstance(free_text, str) or not free_text.strip():
        raise ExtractionError("Progress update text cannot be empty.")

    load_dotenv()

    api_key = os.getenv("GROQ_API_KEY")
    model_name = os.getenv("GROQ_MODEL")

    if not api_key or not model_name:
        raise ModelUnavailableError(
            "Groq API key or model configuration is missing."
        )

    try:
        llm = ChatGroq(
            model=model_name,
            temperature=0,
            api_key=api_key
        )

        structured_llm = llm.with_structured_output(
            ProgressUpdateDraft
        )

    except Exception as e:
        raise ModelUnavailableError(
            f"Could not initialize the Groq model: {e}"
        ) from e

    messages = [
        (
            "system",
            PROGRESS_EXTRACTION_SYSTEM_PROMPT
        ),
        (
            "human",
            f"""
            Task ID: {task_id}

            User Progress Update:
            {free_text}
            """
        )
    ]

    # Retry once if the output cannot be parsed or validated.
    for attempt in range(2):
        try:
            result = structured_llm.invoke(messages)

            if isinstance(result, dict):
                result = ProgressUpdateDraft.model_validate(result)

            if not isinstance(result, ProgressUpdateDraft):
                raise ExtractionError(
                    "The model returned an unexpected output format."
                )

            return result

        except (ValidationError, OutputParserException) as e:

            if attempt == 1:
                raise ExtractionError(
                    f"Model output validation failed after retry: {e}"
                ) from e

        except ExtractionError:
            raise

        except Exception as e:
            raise ModelUnavailableError(
                f"Groq model request failed: {e}"
            ) from e

    raise ExtractionError("Progress extraction failed.")
