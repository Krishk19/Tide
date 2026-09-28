def burst_lines(before: int, after: int, threshold: int = 40) -> int | None:
    """Snapshots are ≤30 s apart, so +40 lines in one snapshot is a paste, not typing.
    The agent never sends unchanged starter files, so the first snapshot counts too."""
    delta = after - before
    return delta if delta >= threshold else None
