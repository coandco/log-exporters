# /// script
# requires-python = ">=3.09"
# dependencies = [
#     "pydantic",
#     "typer",
# ]
# ///

import json
from datetime import datetime
from datetime import timezone as tz
from pathlib import Path
from typing import Annotated

import typer
from pydantic import AliasChoices, BaseModel, BeforeValidator, Field


class Creator(BaseModel):
    name: str
    email: str = ""
    user_type: str


class AttachedFiles(BaseModel):
    original_name: str
    export_name: str


def parse_date(val: str) -> datetime:
    date_format = "%A, %B %d, %Y at %I:%M:%S %p %Z"
    return datetime.strptime(val, date_format).replace(tzinfo=tz.utc).astimezone()


class Message(BaseModel):
    creator: Creator
    # sometimes there's an updated_date instead of created_date -- we want to treat them the same
    date: Annotated[datetime, BeforeValidator(parse_date)] = Field(
        validation_alias=AliasChoices("created_date", "updated_date")
    )
    text: str = ""
    topic_id: str
    message_id: str
    attached_files: list[AttachedFiles] = None

    def __str__(self):
        date_format = "%Y-%m-%d %H:%M:%S"
        attachment_string = (
            f"[{', '.join(x.original_name for x in self.attached_files)}]" if self.attached_files else ""
        )
        return f"[{self.date.strftime(date_format)}] {self.creator.name}: {attachment_string}{self.text}"


def main(root: Path):
    for messages_json_file in root.rglob("messages.json"):
        messages = json.loads(messages_json_file.read_bytes())
        save_location = messages_json_file.parent / "messages.txt"
        with save_location.open("wb") as f:
            for message in messages["messages"]:
                validated_message = Message.model_validate(message)
                f.write(f"{str(validated_message)}\n".encode("utf-8"))


if __name__ == "__main__":
    typer.run(main)
