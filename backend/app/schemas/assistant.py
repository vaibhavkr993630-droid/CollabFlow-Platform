from pydantic import BaseModel


class ThreadSummaryRead(BaseModel):
    summary: str
    comment_count: int
    cached: bool
