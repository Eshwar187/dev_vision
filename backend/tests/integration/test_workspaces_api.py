import pytest
from httpx import AsyncClient


async def _register_and_get_client(client: AsyncClient, email: str, name: str):
    """Helper registering a user and returning their csrf token."""
    res = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "SecurePassword123!",
            "display_name": name,
        },
    )
    assert res.status_code == 201
    return res.cookies.get("devvision_csrf"), res.json()["user"]["id"], res.json()["workspace"]["id"]


@pytest.mark.asyncio
async def test_workspace_crud(async_client: AsyncClient):
    csrf_token, user_id, default_ws_id = await _register_and_get_client(
        async_client, "owner@example.com", "Workspace Owner"
    )

    # 1. Create a second workspace
    create_res = await async_client.post(
        "/api/v1/workspaces",
        json={"name": "DevVision Core"},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert create_res.status_code == 201
    ws2 = create_res.json()
    assert ws2["name"] == "DevVision Core"
    assert ws2["role"] == "owner"
    ws2_id = ws2["id"]

    # 2. List workspaces
    list_res = await async_client.get("/api/v1/workspaces")
    assert list_res.status_code == 200
    workspaces = list_res.json()
    assert len(workspaces) == 2

    # 3. Get single workspace details
    get_res = await async_client.get(f"/api/v1/workspaces/{ws2_id}")
    assert get_res.status_code == 200
    assert get_res.json()["name"] == "DevVision Core"
    assert get_res.json()["member_count"] == 1

    # 4. Update workspace name (PATCH)
    patch_res = await async_client.patch(
        f"/api/v1/workspaces/{ws2_id}",
        json={"name": "DevVision Platform Core"},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["name"] == "DevVision Platform Core"

    # 5. Delete workspace (DELETE)
    del_res = await async_client.delete(
        f"/api/v1/workspaces/{ws2_id}",
        headers={"X-CSRF-Token": csrf_token},
    )
    assert del_res.status_code == 200

    # 6. Verify deleted workspace is gone
    get_deleted = await async_client.get(f"/api/v1/workspaces/{ws2_id}")
    assert get_deleted.status_code == 404


@pytest.mark.asyncio
async def test_slug_collision_handling(async_client: AsyncClient):
    csrf_token, _, _ = await _register_and_get_client(async_client, "slug_user@example.com", "Slug Master")

    res1 = await async_client.post(
        "/api/v1/workspaces",
        json={"name": "Alpha Project"},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert res1.status_code == 201
    assert res1.json()["slug"] == "alpha-project"

    res2 = await async_client.post(
        "/api/v1/workspaces",
        json={"name": "Alpha Project"},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert res2.status_code == 201
    assert res2.json()["slug"] == "alpha-project-1"


@pytest.mark.asyncio
async def test_workspace_isolation_idor_defense(async_client: AsyncClient):
    # User A creates Workspace A
    csrf_a, user_a_id, ws_a_id = await _register_and_get_client(
        async_client, "user_a@example.com", "User Alpha"
    )

    # User B registers in separate session
    from httpx import ASGITransport, AsyncClient as HttpxClient
    from app.main import app as fastapi_app

    transport = ASGITransport(app=fastapi_app)
    async with HttpxClient(transport=transport, base_url="http://test") as client_b:
        csrf_b, user_b_id, ws_b_id = await _register_and_get_client(
            client_b, "user_b@example.com", "User Beta"
        )

        # User B attempts to access User A's workspace
        # IDOR Invariant: Returns 404 WORKSPACE_NOT_FOUND (not 403)
        res_get = await client_b.get(f"/api/v1/workspaces/{ws_a_id}")
        assert res_get.status_code == 404
        assert res_get.json()["error"]["code"] == "WORKSPACE_NOT_FOUND"

        # User B attempts to update User A's workspace
        res_patch = await client_b.patch(
            f"/api/v1/workspaces/{ws_a_id}",
            json={"name": "Hacked Name"},
            headers={"X-CSRF-Token": csrf_b},
        )
        assert res_patch.status_code == 404

        # User B attempts to delete User A's workspace
        res_del = await client_b.delete(
            f"/api/v1/workspaces/{ws_a_id}",
            headers={"X-CSRF-Token": csrf_b},
        )
        assert res_del.status_code == 404

        # User B attempts to list members of User A's workspace
        res_members = await client_b.get(f"/api/v1/workspaces/{ws_a_id}/members")
        assert res_members.status_code == 404


@pytest.mark.asyncio
async def test_member_addition_and_rbac(async_client: AsyncClient):
    # 1. User A (Owner)
    csrf_a, user_a_id, ws_a_id = await _register_and_get_client(
        async_client, "owner_a@example.com", "Owner Alpha"
    )

    # 2. Register User B
    from httpx import ASGITransport, AsyncClient as HttpxClient
    from app.main import app as fastapi_app

    transport = ASGITransport(app=fastapi_app)
    async with HttpxClient(transport=transport, base_url="http://test") as client_b:
        csrf_b, user_b_id, ws_b_id = await _register_and_get_client(
            client_b, "member_b@example.com", "Member Beta"
        )

        # 3. User A adds non-existent user -> 404 USER_NOT_FOUND
        bad_add = await async_client.post(
            f"/api/v1/workspaces/{ws_a_id}/members",
            json={"email": "nobody@example.com", "role": "member"},
            headers={"X-CSRF-Token": csrf_a},
        )
        assert bad_add.status_code == 404
        assert bad_add.json()["error"]["code"] == "USER_NOT_FOUND"

        # 4. User A adds User B as member -> 201
        add_ok = await async_client.post(
            f"/api/v1/workspaces/{ws_a_id}/members",
            json={"email": "member_b@example.com", "role": "member"},
            headers={"X-CSRF-Token": csrf_a},
        )
        assert add_ok.status_code == 201

        # 5. User A tries to add User B again -> 409 MEMBER_ALREADY_EXISTS
        dup_add = await async_client.post(
            f"/api/v1/workspaces/{ws_a_id}/members",
            json={"email": "member_b@example.com", "role": "member"},
            headers={"X-CSRF-Token": csrf_a},
        )
        assert dup_add.status_code == 409
        assert dup_add.json()["error"]["code"] == "MEMBER_ALREADY_EXISTS"

        # 6. User B can now read Workspace A
        res_member_read = await client_b.get(f"/api/v1/workspaces/{ws_a_id}")
        assert res_member_read.status_code == 200
        assert res_member_read.json()["role"] == "member"

        # 7. User B (member) CANNOT update workspace name -> 403 FORBIDDEN
        member_update = await client_b.patch(
            f"/api/v1/workspaces/{ws_a_id}",
            json={"name": "Member Unauthorized Edit"},
            headers={"X-CSRF-Token": csrf_b},
        )
        assert member_update.status_code == 403

        # 8. User B (member) CANNOT delete workspace -> 403 FORBIDDEN
        member_delete = await client_b.delete(
            f"/api/v1/workspaces/{ws_a_id}",
            headers={"X-CSRF-Token": csrf_b},
        )
        assert member_delete.status_code == 403


@pytest.mark.asyncio
async def test_last_owner_protection_and_ownership_transfer(async_client: AsyncClient):
    # Register Owner A
    csrf_a, user_a_id, ws_a_id = await _register_and_get_client(
        async_client, "solitary_owner@example.com", "Solitary Owner"
    )

    # 1. Attempt to remove sole owner -> 400 CANNOT_REMOVE_LAST_OWNER
    remove_last = await async_client.delete(
        f"/api/v1/workspaces/{ws_a_id}/members/{user_a_id}",
        headers={"X-CSRF-Token": csrf_a},
    )
    assert remove_last.status_code == 400
    assert remove_last.json()["error"]["code"] == "CANNOT_REMOVE_LAST_OWNER"

    # 2. Attempt to demote sole owner to admin -> 400 CANNOT_REMOVE_LAST_OWNER
    demote_last = await async_client.patch(
        f"/api/v1/workspaces/{ws_a_id}/members/{user_a_id}",
        json={"role": "admin"},
        headers={"X-CSRF-Token": csrf_a},
    )
    assert demote_last.status_code == 400
    assert demote_last.json()["error"]["code"] == "CANNOT_REMOVE_LAST_OWNER"

    # Register User B and add to workspace
    from httpx import ASGITransport, AsyncClient as HttpxClient
    from app.main import app as fastapi_app

    transport = ASGITransport(app=fastapi_app)
    async with HttpxClient(transport=transport, base_url="http://test") as client_b:
        csrf_b, user_b_id, _ = await _register_and_get_client(
            client_b, "successor@example.com", "Successor"
        )

        await async_client.post(
            f"/api/v1/workspaces/{ws_a_id}/members",
            json={"email": "successor@example.com", "role": "admin"},
            headers={"X-CSRF-Token": csrf_a},
        )

        # 3. Ownership transfer to self is rejected
        transfer_self = await async_client.post(
            f"/api/v1/workspaces/{ws_a_id}/transfer-ownership",
            json={"new_owner_user_id": user_a_id},
            headers={"X-CSRF-Token": csrf_a},
        )
        assert transfer_self.status_code == 400

        # 4. Ownership transfer to User B succeeds
        transfer_ok = await async_client.post(
            f"/api/v1/workspaces/{ws_a_id}/transfer-ownership",
            json={"new_owner_user_id": user_b_id},
            headers={"X-CSRF-Token": csrf_a},
        )
        assert transfer_ok.status_code == 200

        # 5. Verify User B is now owner and User A is now admin
        ws_details_a = await async_client.get(f"/api/v1/workspaces/{ws_a_id}")
        assert ws_details_a.json()["role"] == "admin"

        ws_details_b = await client_b.get(f"/api/v1/workspaces/{ws_a_id}")
        assert ws_details_b.json()["role"] == "owner"