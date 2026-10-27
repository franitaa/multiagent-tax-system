"""A real-looking SSN must not reach state["messages"], even when the graph is called directly
(not through the chat page, which cleans text itself). Practice numbers (900-999) are kept."""
import pytest

from security import SSN_REMOVED, remove_real_ssns
from src.state import append_messages


@pytest.mark.parametrize("text", ["123-45-6789", "123456789", "123 45 6789", "my number is 078-05-1120."])
def test_real_looking_ssn_is_removed(text):
    cleaned = remove_real_ssns(text)
    assert SSN_REMOVED in cleaned
    assert not any(ch.isdigit() for ch in cleaned)


def test_practice_ssn_is_kept():
    assert remove_real_ssns("912-34-5678") == "912-34-5678"


def test_state_reducer_cleans_new_messages_and_keeps_old():
    old = [{"role": "assistant", "content": "Hello"}]
    merged = append_messages(old, [{"role": "user", "content": "it is 123-45-6789"}])
    assert merged[0] == old[0]
    assert merged[1]["content"] == f"it is {SSN_REMOVED}"


def test_reducer_tolerates_odd_messages():
    assert append_messages(None, None) == []
    assert append_messages([], [{"role": "user"}]) == [{"role": "user"}]
