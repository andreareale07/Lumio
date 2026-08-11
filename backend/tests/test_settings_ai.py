from httpx import AsyncClient


async def _register(client: AsyncClient, email: str) -> str:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-password-123", "display_name": "Test"},
    )
    return response.json()["access_token"]


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _create_profile(client: AsyncClient, token: str, **overrides) -> dict:
    payload = {"name": "Profilo", "provider": "ollama", "endpoint": "http://ollama:11434", "model": "gemma3:4b"}
    payload.update(overrides)
    response = await client.post("/api/v1/settings/ai/profiles", json=payload, headers=_auth_headers(token))
    assert response.status_code == 201, response.text
    return response.json()


async def test_no_profiles_by_default(client):
    token = await _register(client, "ai-default@example.com")
    response = await client.get("/api/v1/settings/ai/profiles", headers=_auth_headers(token))
    assert response.status_code == 200
    assert response.json() == []


async def test_create_ollama_profile_requires_endpoint_and_model(client):
    token = await _register(client, "ai-ollama-incomplete@example.com")
    response = await client.post(
        "/api/v1/settings/ai/profiles",
        json={"name": "Ollama", "provider": "ollama"},
        headers=_auth_headers(token),
    )
    assert response.status_code == 400


async def test_create_ollama_profile_is_inactive_by_default(client):
    token = await _register(client, "ai-ollama-valid@example.com")
    profile = await _create_profile(client, token)
    assert profile["provider"] == "ollama"
    assert profile["endpoint"] == "http://ollama:11434"
    assert profile["api_key_set"] is False
    assert profile["is_active"] is False


async def test_create_openai_profile_requires_api_key(client):
    token = await _register(client, "ai-openai-nokey@example.com")
    response = await client.post(
        "/api/v1/settings/ai/profiles",
        json={"name": "OpenAI", "provider": "openai", "model": "gpt-4o-mini"},
        headers=_auth_headers(token),
    )
    assert response.status_code == 400


async def test_openai_api_key_never_returned_in_plaintext(client):
    token = await _register(client, "ai-openai-key@example.com")
    response = await client.post(
        "/api/v1/settings/ai/profiles",
        json={"name": "OpenAI", "provider": "openai", "model": "gpt-4o-mini", "api_key": "sk-super-secret"},
        headers=_auth_headers(token),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["api_key_set"] is True
    assert "api_key" not in body
    assert "sk-super-secret" not in response.text


async def test_omitting_api_key_on_patch_keeps_existing_key(client):
    token = await _register(client, "ai-openai-keep-key@example.com")
    profile = await _create_profile(
        client, token, name="OpenAI", provider="openai", model="gpt-4o-mini", api_key="sk-super-secret",
        endpoint=None,
    )
    response = await client.patch(
        f"/api/v1/settings/ai/profiles/{profile['id']}",
        json={"model": "gpt-4o-2024"},
        headers=_auth_headers(token),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["model"] == "gpt-4o-2024"
    assert body["api_key_set"] is True


async def test_empty_string_api_key_on_patch_clears_it(client):
    token = await _register(client, "ai-custom-clear-key@example.com")
    profile = await _create_profile(
        client, token, name="Custom", provider="custom", endpoint="http://localhost:8080/v1",
        model="local-model", api_key="sk-optional-secret",
    )
    response = await client.patch(
        f"/api/v1/settings/ai/profiles/{profile['id']}", json={"api_key": ""}, headers=_auth_headers(token)
    )
    assert response.status_code == 200
    assert response.json()["api_key_set"] is False


async def test_patch_cannot_change_provider(client):
    token = await _register(client, "ai-patch-no-provider-change@example.com")
    profile = await _create_profile(client, token)
    response = await client.patch(
        f"/api/v1/settings/ai/profiles/{profile['id']}",
        json={"provider": "openai"},
        headers=_auth_headers(token),
    )
    assert response.status_code == 200
    assert response.json()["provider"] == "ollama"


async def test_activating_a_profile_deactivates_the_previously_active_one(client):
    token = await _register(client, "ai-activate-exclusive@example.com")
    profile_a = await _create_profile(client, token, name="A")
    profile_b = await _create_profile(client, token, name="B", endpoint="http://ollama-b:11434")

    activate_a = await client.post(
        f"/api/v1/settings/ai/profiles/{profile_a['id']}/activate", headers=_auth_headers(token)
    )
    assert activate_a.status_code == 200
    assert activate_a.json()["is_active"] is True

    activate_b = await client.post(
        f"/api/v1/settings/ai/profiles/{profile_b['id']}/activate", headers=_auth_headers(token)
    )
    assert activate_b.status_code == 200
    assert activate_b.json()["is_active"] is True

    profiles = (await client.get("/api/v1/settings/ai/profiles", headers=_auth_headers(token))).json()
    active_ids = [p["id"] for p in profiles if p["is_active"]]
    assert active_ids == [profile_b["id"]]


async def test_deactivate_clears_the_active_profile(client):
    token = await _register(client, "ai-deactivate@example.com")
    profile = await _create_profile(client, token)
    await client.post(f"/api/v1/settings/ai/profiles/{profile['id']}/activate", headers=_auth_headers(token))

    response = await client.post("/api/v1/settings/ai/deactivate", headers=_auth_headers(token))
    assert response.status_code == 204

    profiles = (await client.get("/api/v1/settings/ai/profiles", headers=_auth_headers(token))).json()
    assert all(not p["is_active"] for p in profiles)


async def test_delete_profile(client):
    token = await _register(client, "ai-delete@example.com")
    profile = await _create_profile(client, token)
    response = await client.delete(f"/api/v1/settings/ai/profiles/{profile['id']}", headers=_auth_headers(token))
    assert response.status_code == 204

    profiles = (await client.get("/api/v1/settings/ai/profiles", headers=_auth_headers(token))).json()
    assert profiles == []


async def test_draft_test_connection_reports_failure_without_raising(client):
    token = await _register(client, "ai-test-fail@example.com")
    response = await client.post(
        "/api/v1/settings/ai/test",
        json={"provider": "ollama", "endpoint": "http://unreachable.invalid:11434"},
        headers=_auth_headers(token),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["message"]


async def test_draft_test_connection_for_ollama_does_not_require_a_model(client):
    token = await _register(client, "ai-test-no-model@example.com")
    response = await client.post(
        "/api/v1/settings/ai/test",
        json={"provider": "ollama", "endpoint": "http://unreachable.invalid:11434"},
        headers=_auth_headers(token),
    )
    assert response.status_code == 200
    assert response.json()["success"] is False  # endpoint irraggiungibile, ma non per validazione


async def test_draft_list_models_for_ollama(client, httpx_mock):
    token = await _register(client, "ai-models-ollama@example.com")
    httpx_mock.add_response(
        url="http://fake-ollama.local:11434/api/tags",
        json={"models": [{"name": "gemma3:4b"}, {"name": "llama3.1:8b"}]},
    )
    response = await client.post(
        "/api/v1/settings/ai/models",
        json={"provider": "ollama", "endpoint": "http://fake-ollama.local:11434"},
        headers=_auth_headers(token),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["models"] == ["gemma3:4b", "llama3.1:8b"]


async def test_draft_list_models_requires_endpoint_for_ollama(client):
    token = await _register(client, "ai-models-no-endpoint@example.com")
    response = await client.post(
        "/api/v1/settings/ai/models", json={"provider": "ollama"}, headers=_auth_headers(token)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["models"] == []


async def test_draft_list_models_for_custom_provider_fails_gracefully_when_unsupported(client, httpx_mock):
    token = await _register(client, "ai-models-custom@example.com")
    httpx_mock.add_response(url="http://fake-custom.local/v1/models", status_code=404)
    response = await client.post(
        "/api/v1/settings/ai/models",
        json={"provider": "custom", "endpoint": "http://fake-custom.local/v1"},
        headers=_auth_headers(token),
    )
    assert response.status_code == 200
    body = response.json()
    # Nessun errore per una feature opzionale su un provider che non la
    # supporta: la UI ricade sul campo di testo libero.
    assert body["success"] is True
    assert body["models"] == []


async def test_saved_profile_test_connection_and_list_models(client, httpx_mock):
    token = await _register(client, "ai-saved-test@example.com")
    profile = await _create_profile(client, token, endpoint="http://fake-ollama-saved.local:11434")

    httpx_mock.add_response(url="http://fake-ollama-saved.local:11434/api/tags", json={"models": []})
    test_response = await client.post(
        f"/api/v1/settings/ai/profiles/{profile['id']}/test", headers=_auth_headers(token)
    )
    assert test_response.status_code == 200
    assert test_response.json()["success"] is True

    httpx_mock.add_response(
        url="http://fake-ollama-saved.local:11434/api/tags", json={"models": [{"name": "gemma3:4b"}]}
    )
    models_response = await client.post(
        f"/api/v1/settings/ai/profiles/{profile['id']}/models", headers=_auth_headers(token)
    )
    assert models_response.status_code == 200
    assert models_response.json()["models"] == ["gemma3:4b"]


async def test_user_a_cannot_see_or_modify_user_b_profile(client):
    token_a = await _register(client, "ai-iso-a@example.com")
    token_b = await _register(client, "ai-iso-b@example.com")

    profile_b = await _create_profile(client, token_b)

    list_a = await client.get("/api/v1/settings/ai/profiles", headers=_auth_headers(token_a))
    assert list_a.json() == []

    get_a = await client.patch(
        f"/api/v1/settings/ai/profiles/{profile_b['id']}",
        json={"model": "hacked"},
        headers=_auth_headers(token_a),
    )
    assert get_a.status_code == 404

    activate_a = await client.post(
        f"/api/v1/settings/ai/profiles/{profile_b['id']}/activate", headers=_auth_headers(token_a)
    )
    assert activate_a.status_code == 404

    delete_a = await client.delete(
        f"/api/v1/settings/ai/profiles/{profile_b['id']}", headers=_auth_headers(token_a)
    )
    assert delete_a.status_code == 404
