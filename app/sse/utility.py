def construct_sse(event, data) -> bytes:
    """Construct SSE-formatted bytes for a single event."""
    lines = []
    if event:
        lines.append(f"event: {event}")
    for line in (data.splitlines() or [""]):
        lines.append(f"data: {line}")
    return ("\n".join(lines) + "\n\n").encode("utf-8")
