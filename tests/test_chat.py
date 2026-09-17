import json

from tests.test_conversations import upload_ready_document


async def start_conversation(client, headers):
    document_id = await upload_ready_document(client, headers)
    response = await client.post(
        "/conversations/", json={"document_id": document_id}, headers=headers
    )
    return response.json()["id"]


async def test_chat_answers_with_the_model(client, headers, fake_llm):
    conversation_id = await start_conversation(client, headers)

    response = await client.post(
        f"/conversations/{conversation_id}/chat",
        json={"question": "How did European revenue change?"},
        headers=headers,
    )
    body = response.json()

    assert response.status_code == 200
    assert body["answer"] == "European revenue grew twelve percent [1]."
    assert body["model"] == "claude-opus-5-stub"
    assert body["sources"]


async def test_the_prompt_carries_the_retrieved_excerpts(client, headers, fake_llm):
    conversation_id = await start_conversation(client, headers)

    await client.post(
        f"/conversations/{conversation_id}/chat",
        json={"question": "How did European revenue change?"},
        headers=headers,
    )

    prompt = fake_llm[0]
    assert "report.txt" in prompt["system"]
    assert "Cite the excerpts" in prompt["system"]

    user_turn = prompt["messages"][-1]["content"]
    assert "<excerpts>" in user_turn
    assert "European revenue grew" in user_turn
    assert "How did European revenue change?" in user_turn


async def test_both_turns_are_persisted(client, headers, fake_llm):
    conversation_id = await start_conversation(client, headers)

    await client.post(
        f"/conversations/{conversation_id}/chat",
        json={"question": "How did European revenue change?"},
        headers=headers,
    )

    messages = (
        await client.get(f"/conversations/{conversation_id}/messages", headers=headers)
    ).json()

    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert messages[0]["content"] == "How did European revenue change?"
    assert messages[1]["sources"]
    assert messages[1]["sources"][0]["marker"] == 1


async def test_sources_carry_citation_metadata(client, headers, fake_llm):
    conversation_id = await start_conversation(client, headers)

    response = await client.post(
        f"/conversations/{conversation_id}/chat",
        json={"question": "What is the operational risk?"},
        headers=headers,
    )

    source = response.json()["sources"][0]
    assert source["document_filename"] == "report.txt"
    assert source["page_number"] == 1
    assert "content" in source and source["content"]


async def test_earlier_turns_are_replayed_to_the_model(client, headers, fake_llm):
    conversation_id = await start_conversation(client, headers)

    await client.post(
        f"/conversations/{conversation_id}/chat",
        json={"question": "First question?"},
        headers=headers,
    )
    await client.post(
        f"/conversations/{conversation_id}/chat",
        json={"question": "Second question?"},
        headers=headers,
    )

    second_prompt = fake_llm[1]["messages"]
    roles = [turn["role"] for turn in second_prompt]

    assert roles == ["user", "assistant", "user"]
    assert second_prompt[0]["content"] == "First question?"
    assert "Second question?" in second_prompt[-1]["content"]


async def test_chat_without_an_api_key_falls_back_to_excerpts(client, headers):
    conversation_id = await start_conversation(client, headers)

    response = await client.post(
        f"/conversations/{conversation_id}/chat",
        json={"question": "How did European revenue change?"},
        headers=headers,
    )
    body = response.json()

    assert response.status_code == 200
    assert body["model"] == "extractive-fallback"
    assert "ANTHROPIC_API_KEY" in body["answer"]
    assert "European revenue grew" in body["answer"]
    assert body["sources"]


async def test_chat_streams_server_sent_events(client, headers, fake_llm):
    conversation_id = await start_conversation(client, headers)

    async with client.stream(
        "POST",
        f"/conversations/{conversation_id}/chat/stream",
        json={"question": "How did European revenue change?"},
        headers=headers,
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        payload = "".join([chunk async for chunk in response.aiter_text()])

    events = [line[7:] for line in payload.splitlines() if line.startswith("event: ")]
    data = [json.loads(line[6:]) for line in payload.splitlines() if line.startswith("data: ")]

    assert events[0] == "sources"
    assert "delta" in events
    assert events[-1] == "done"
    assert "".join(item for item in data if isinstance(item, str)) == (
        "European revenue grew twelve percent [1]."
    )


async def test_the_streamed_answer_is_persisted(client, headers, fake_llm):
    conversation_id = await start_conversation(client, headers)

    async with client.stream(
        "POST",
        f"/conversations/{conversation_id}/chat/stream",
        json={"question": "How did European revenue change?"},
        headers=headers,
    ) as response:
        async for _ in response.aiter_text():
            pass

    messages = (
        await client.get(f"/conversations/{conversation_id}/messages", headers=headers)
    ).json()

    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert messages[1]["content"] == "European revenue grew twelve percent [1]."


async def test_cannot_chat_in_another_users_conversation(
    client, headers, make_user, auth_headers, fake_llm
):
    other = await make_user()
    conversation_id = await start_conversation(client, await auth_headers(other.email))

    response = await client.post(
        f"/conversations/{conversation_id}/chat",
        json={"question": "Anything?"},
        headers=headers,
    )
    assert response.status_code == 404


async def test_chat_requires_authentication(client, headers, fake_llm):
    conversation_id = await start_conversation(client, headers)

    response = await client.post(
        f"/conversations/{conversation_id}/chat", json={"question": "Anything?"}
    )
    assert response.status_code == 401


async def test_an_empty_question_is_rejected(client, headers, fake_llm):
    conversation_id = await start_conversation(client, headers)

    response = await client.post(
        f"/conversations/{conversation_id}/chat", json={"question": ""}, headers=headers
    )
    assert response.status_code == 422


async def test_conversation_detail_includes_messages(client, headers, fake_llm):
    conversation_id = await start_conversation(client, headers)
    await client.post(
        f"/conversations/{conversation_id}/chat",
        json={"question": "How did European revenue change?"},
        headers=headers,
    )

    response = await client.get(f"/conversations/{conversation_id}", headers=headers)

    assert len(response.json()["messages"]) == 2
