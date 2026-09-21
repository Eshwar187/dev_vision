<script lang="ts">
  import { onMount } from "svelte";
  import { page } from "$app/stores";
  import { api } from "$lib/api/client";
  import { currentUser } from "$lib/stores/auth";
  import { workspaces, activeWorkspace, fetchWorkspaces, setActiveWorkspace } from "$lib/stores/workspace";
  import type { WorkspaceDetail, WorkspaceMember, GitHubInstallation } from "$lib/api/types";
  import RepositoryPickerModal from "$lib/components/github/RepositoryPickerModal.svelte";

  // State
  let selectedWsDetail: WorkspaceDetail | null = null;
  let membersList: WorkspaceMember[] = [];
  let gitHubInstallations: GitHubInstallation[] = [];
  let isLoadingDetail = false;
  let isLoadingGitHub = false;
  let isConnectingGitHub = false;
  let showRepoPickerModal = false;
  let actionMessage = "";
  let actionError = "";

  // Modals & forms
  let showCreateModal = false;
  let newWorkspaceName = "";
  let isCreating = false;

  let showRenameModal = false;
  let renameWorkspaceName = "";
  let isRenaming = false;

  let showAddMemberModal = false;
  let newMemberEmail = "";
  let newMemberRole: "admin" | "member" = "member";
  let isAddingMember = false;

  let showTransferModal = false;
  let newOwnerUserId = "";
  let isTransferring = false;

  $: activeWsId = $activeWorkspace?.id;
  $: if (activeWsId) {
    loadWorkspaceDetails(activeWsId);
  }

  onMount(() => {
    // Check if returning from GitHub OAuth flow
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get("github_connected") === "true") {
      actionMessage = "GitHub App successfully authorized and connected to this workspace!";
      // Clean up query string cleanly
      window.history.replaceState({}, document.title, window.location.pathname);
    }
  });

  async function loadWorkspaceDetails(id: string) {
    isLoadingDetail = true;
    isLoadingGitHub = true;
    actionError = "";
    actionMessage = "";
    const [detailRes, membersRes, githubRes] = await Promise.all([
      api.getWorkspace(id),
      api.listMembers(id),
      api.listGitHubInstallations(id),
    ]);
    isLoadingDetail = false;
    isLoadingGitHub = false;

    if (detailRes.success && detailRes.data) {
      selectedWsDetail = detailRes.data;
    }
    if (membersRes.success && membersRes.data?.members) {
      membersList = membersRes.data.members;
    }
    if (githubRes.success && githubRes.data?.items) {
      gitHubInstallations = githubRes.data.items;
    }
  }

  async function handleConnectGitHub() {
    if (!selectedWsDetail) return;
    isConnectingGitHub = true;
    actionError = "";
    actionMessage = "";

    const res = await api.initGitHubConnect(selectedWsDetail.id);
    isConnectingGitHub = false;

    if (res.success && res.data) {
      // Redirect browser to GitHub App installation / authorization URL
      window.location.href = res.data.authorization_url;
    } else {
      actionError = res.error || "Failed to initialize GitHub App authorization.";
    }
  }

  async function handleDisconnectGitHub(installationId: string, accountLogin: string) {
    if (!selectedWsDetail) return;
    if (!confirm(`Are you sure you want to disconnect GitHub account "${accountLogin}"? Any repositories attached via this installation will become detached.`)) {
      return;
    }

    actionError = "";
    actionMessage = "";
    const res = await api.deleteGitHubInstallation(selectedWsDetail.id, installationId);

    if (res.success) {
      actionMessage = `GitHub account "${accountLogin}" disconnected successfully.`;
      await loadWorkspaceDetails(selectedWsDetail.id);
    } else {
      actionError = res.error || "Failed to disconnect GitHub installation.";
    }
  }

  async function handleCreateWorkspace() {
    if (!newWorkspaceName.trim()) return;
    isCreating = true;
    actionError = "";
    actionMessage = "";

    const res = await api.createWorkspace(newWorkspaceName.trim());
    isCreating = false;

    if (res.success && res.data) {
      showCreateModal = false;
      newWorkspaceName = "";
      actionMessage = "Workspace created successfully.";
      const updated = await fetchWorkspaces();
      const created = updated.find((w) => w.id === res.data?.id);
      if (created) setActiveWorkspace(created);
    } else {
      actionError = res.error || "Failed to create workspace.";
    }
  }

  async function handleRenameWorkspace() {
    if (!selectedWsDetail || !renameWorkspaceName.trim()) return;
    isRenaming = true;
    actionError = "";
    actionMessage = "";

    const res = await api.updateWorkspace(selectedWsDetail.id, renameWorkspaceName.trim());
    isRenaming = false;

    if (res.success && res.data) {
      showRenameModal = false;
      actionMessage = "Workspace renamed successfully.";
      await fetchWorkspaces();
      await loadWorkspaceDetails(selectedWsDetail.id);
    } else {
      actionError = res.error || "Failed to rename workspace.";
    }
  }

  async function handleDeleteWorkspace() {
    if (!selectedWsDetail) return;
    const confirmDelete = confirm(
      `Are you sure you want to permanently delete workspace "${selectedWsDetail.name}"? This action cannot be undone.`
    );
    if (!confirmDelete) return;

    actionError = "";
    actionMessage = "";
    const res = await api.deleteWorkspace(selectedWsDetail.id);

    if (res.success) {
      actionMessage = "Workspace deleted successfully.";
      const remaining = await fetchWorkspaces();
      if (remaining.length > 0) {
        setActiveWorkspace(remaining[0]);
      } else {
        selectedWsDetail = null;
        membersList = [];
      }
    } else {
      actionError = res.error || "Failed to delete workspace.";
    }
  }

  async function handleAddMember() {
    if (!selectedWsDetail || !newMemberEmail.trim()) return;
    isAddingMember = true;
    actionError = "";
    actionMessage = "";

    const res = await api.addMember(selectedWsDetail.id, newMemberEmail.trim(), newMemberRole);
    isAddingMember = false;

    if (res.success) {
      showAddMemberModal = false;
      newMemberEmail = "";
      actionMessage = "Member added successfully.";
      await loadWorkspaceDetails(selectedWsDetail.id);
    } else {
      actionError = res.error || "Failed to add member.";
    }
  }

  async function handleRoleChange(userId: string, newRole: "admin" | "member") {
    if (!selectedWsDetail) return;
    actionError = "";
    actionMessage = "";

    const res = await api.updateMemberRole(selectedWsDetail.id, userId, newRole);
    if (res.success) {
      actionMessage = "Member role updated.";
      await loadWorkspaceDetails(selectedWsDetail.id);
      await fetchWorkspaces();
    } else {
      actionError = res.error || "Failed to update member role.";
    }
  }

  function onMemberRoleSelect(userId: string, event: Event) {
    const target = event.target as HTMLSelectElement;
    const value = target.value;
    if (value === "admin" || value === "member") {
      handleRoleChange(userId, value);
    }
  }

  async function handleRemoveMember(userId: string, memberEmail: string) {
    if (!selectedWsDetail) return;
    const confirmRemove = confirm(`Remove ${memberEmail} from this workspace?`);
    if (!confirmRemove) return;

    actionError = "";
    actionMessage = "";
    const res = await api.removeMember(selectedWsDetail.id, userId);

    if (res.success) {
      actionMessage = "Member removed.";
      await loadWorkspaceDetails(selectedWsDetail.id);
    } else {
      actionError = res.error || "Failed to remove member.";
    }
  }

  async function handleTransferOwnership() {
    if (!selectedWsDetail || !newOwnerUserId) return;
    isTransferring = true;
    actionError = "";
    actionMessage = "";

    const res = await api.transferOwnership(selectedWsDetail.id, newOwnerUserId);
    isTransferring = false;

    if (res.success) {
      showTransferModal = false;
      actionMessage = "Workspace ownership transferred successfully.";
      await fetchWorkspaces();
      await loadWorkspaceDetails(selectedWsDetail.id);
    } else {
      actionError = res.error || "Failed to transfer ownership.";
    }
  }
</script>

<div class="space-y-8">
  <!-- Header with Actions -->
  <div class="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
    <div>
      <h1 class="text-2xl font-bold tracking-tight text-white">Workspaces</h1>
      <p class="text-xs text-slate-400 mt-1">
        Manage workspace tenant boundaries, team members, and role-based permissions.
      </p>
    </div>

    <button
      on:click={() => { showCreateModal = true; actionError = ""; }}
      class="inline-flex items-center gap-2 px-4 py-2 text-xs font-medium rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white transition-all shadow-md shadow-cyan-600/20 active:scale-95 self-start md:self-auto"
    >
      + New Workspace
    </button>
  </div>

  <!-- Action Banners -->
  {#if actionMessage}
    <div class="p-3 rounded-lg bg-emerald-950/80 border border-emerald-800 text-emerald-300 text-xs">
      {actionMessage}
    </div>
  {/if}

  {#if actionError}
    <div class="p-3 rounded-lg bg-rose-950/80 border border-rose-800 text-rose-300 text-xs">
      {actionError}
    </div>
  {/if}

  <!-- Main Management View -->
  <div class="grid grid-cols-1 lg:grid-cols-4 gap-6">
    <!-- Workspaces List Column -->
    <div class="space-y-3">
      <h3 class="text-xs font-semibold uppercase tracking-wider text-slate-400">Your Workspaces</h3>
      <div class="space-y-2">
        {#each $workspaces as ws (ws.id)}
          <button
            on:click={() => setActiveWorkspace(ws)}
            class="w-full text-left p-3 rounded-lg border transition-all {ws.id === $activeWorkspace?.id
              ? 'bg-cyan-950/40 border-cyan-700/80 text-white shadow-sm'
              : 'bg-slate-900/50 border-slate-800 text-slate-300 hover:bg-slate-900 hover:border-slate-700'}"
          >
            <div class="flex items-center justify-between">
              <span class="font-medium text-sm truncate">{ws.name}</span>
              <span class="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-slate-800 text-slate-400">
                {ws.role}
              </span>
            </div>
            <div class="text-[11px] text-slate-500 font-mono truncate mt-1">/{ws.slug}</div>
          </button>
        {/each}
      </div>
    </div>

    <!-- Active Workspace Detail Column -->
    <div class="lg:col-span-3 space-y-6">
      {#if selectedWsDetail}
        <!-- Workspace Summary & Controls -->
        <div class="rounded-xl border border-slate-800 bg-slate-900/50 p-6 space-y-4">
          <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <div>
              <div class="flex items-center gap-2">
                <h2 class="text-xl font-bold text-white">{selectedWsDetail.name}</h2>
                <span class="text-xs px-2 py-0.5 rounded-full bg-cyan-950 border border-cyan-800 text-cyan-300 font-mono capitalize">
                  {selectedWsDetail.role}
                </span>
              </div>
              <p class="text-xs text-slate-400 mt-1 font-mono">slug: {selectedWsDetail.slug} &bull; ID: {selectedWsDetail.id}</p>
            </div>

            <!-- Workspace Action Buttons -->
            <div class="flex items-center gap-2">
              {#if selectedWsDetail.role === "owner" || selectedWsDetail.role === "admin"}
                <button
                  on:click={() => {
                    renameWorkspaceName = selectedWsDetail?.name || "";
                    showRenameModal = true;
                  }}
                  class="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-xs text-slate-200 transition-colors"
                >
                  Rename
                </button>
              {/if}

              {#if selectedWsDetail.role === "owner"}
                <button
                  on:click={() => { showTransferModal = true; }}
                  class="px-3 py-1.5 rounded-lg bg-amber-950/60 hover:bg-amber-900/80 border border-amber-800 text-xs text-amber-300 transition-colors"
                >
                  Transfer Ownership
                </button>
                <button
                  on:click={handleDeleteWorkspace}
                  class="px-3 py-1.5 rounded-lg bg-rose-950/60 hover:bg-rose-900/80 border border-rose-800 text-xs text-rose-300 transition-colors"
                >
                  Delete
                </button>
              {/if}
            </div>
          </div>
        </div>

        <!-- Team Members Section -->
        <div class="rounded-xl border border-slate-800 bg-slate-900/40 p-6 space-y-4">
          <div class="flex items-center justify-between">
            <div>
              <h3 class="text-sm font-semibold text-white">Members & Permissions</h3>
              <p class="text-xs text-slate-400">Team members with access to this tenant workspace.</p>
            </div>

            {#if selectedWsDetail.role === "owner" || selectedWsDetail.role === "admin"}
              <button
                on:click={() => { showAddMemberModal = true; }}
                class="px-3 py-1.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-medium transition-colors"
              >
                + Add Member
              </button>
            {/if}
          </div>

          <!-- Members Table -->
          <div class="overflow-x-auto">
            <table class="w-full text-left text-xs">
              <thead class="text-slate-400 border-b border-slate-800">
                <tr>
                  <th class="py-2.5 px-3">User</th>
                  <th class="py-2.5 px-3">Role</th>
                  <th class="py-2.5 px-3">Joined</th>
                  <th class="py-2.5 px-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-slate-800/60">
                {#each membersList as member (member.user_id)}
                  <tr class="hover:bg-slate-900/30">
                    <td class="py-3 px-3">
                      <div class="font-medium text-slate-200">{member.display_name}</div>
                      <div class="text-[11px] text-slate-500">{member.email}</div>
                    </td>
                    <td class="py-3 px-3">
                      {#if selectedWsDetail.role === "owner" && member.role !== "owner"}
                        <select
                          value={member.role}
                          on:change={(e) => onMemberRoleSelect(member.user_id, e)}
                          class="bg-slate-950 border border-slate-800 text-slate-300 rounded px-2 py-1 text-xs focus:outline-none focus:border-cyan-500"
                        >
                          <option value="member">member</option>
                          <option value="admin">admin</option>
                        </select>
                      {:else}
                        <span class="px-2 py-0.5 rounded uppercase font-mono text-[10px] {member.role === 'owner' ? 'bg-cyan-950 text-cyan-400 border border-cyan-800' : 'bg-slate-800 text-slate-400'}">
                          {member.role}
                        </span>
                      {/if}
                    </td>
                    <td class="py-3 px-3 text-slate-400 text-[11px]">
                      {new Date(member.joined_at).toLocaleDateString()}
                    </td>
                    <td class="py-3 px-3 text-right">
                      {#if selectedWsDetail.role === "owner" && member.role !== "owner"}
                        <button
                          on:click={() => handleRemoveMember(member.user_id, member.email)}
                          class="text-rose-400 hover:text-rose-300 transition-colors"
                        >
                          Remove
                        </button>
                      {:else if member.user_id === $currentUser?.id && member.role !== "owner"}
                        <button
                          on:click={() => handleRemoveMember(member.user_id, member.email)}
                          class="text-slate-400 hover:text-rose-400 transition-colors"
                        >
                          Leave
                        </button>
                      {:else}
                        <span class="text-slate-600">—</span>
                      {/if}
                    </td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        </div>

        <!-- GitHub App Integration Section -->
        <div class="rounded-xl border border-slate-800 bg-slate-900/40 p-6 space-y-4">
          <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <div>
              <div class="flex items-center gap-2">
                <svg class="w-5 h-5 text-white" fill="currentColor" viewBox="0 0 24 24">
                  <path fill-rule="evenodd" clip-rule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" />
                </svg>
                <h3 class="text-sm font-semibold text-white">GitHub Integration</h3>
              </div>
              <p class="text-xs text-slate-400 mt-1">
                Authorize DevVision GitHub App to discover and synchronize repositories into Codebase Intelligence.
              </p>
            </div>

            <div class="flex items-center gap-2">
              {#if gitHubInstallations.length > 0}
                <button
                  on:click={() => (showRepoPickerModal = true)}
                  class="px-3 py-1.5 rounded-lg bg-cyan-600/90 hover:bg-cyan-500 text-white text-xs font-medium transition-colors flex items-center gap-1.5"
                >
                  <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
                  </svg>
                  Attach Repositories
                </button>
              {/if}

              {#if selectedWsDetail.role === "owner" || selectedWsDetail.role === "admin"}
                <button
                  on:click={handleConnectGitHub}
                  disabled={isConnectingGitHub}
                  class="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-white text-xs font-medium transition-colors flex items-center gap-1.5 disabled:opacity-50"
                >
                  {#if isConnectingGitHub}
                    <div class="animate-spin rounded-full h-3 w-3 border-b-2 border-white"></div>
                    Connecting...
                  {:else}
                    <svg class="w-3.5 h-3.5 text-slate-300" fill="currentColor" viewBox="0 0 24 24">
                      <path fill-rule="evenodd" clip-rule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" />
                    </svg>
                    Install / Connect App
                  {/if}
                </button>
              {/if}
            </div>
          </div>

          <!-- Installations List -->
          {#if isLoadingGitHub}
            <div class="py-6 flex items-center justify-center gap-2 text-xs text-slate-400 font-mono">
              <div class="animate-spin rounded-full h-4 w-4 border-b-2 border-cyan-500"></div>
              Loading connected accounts...
            </div>
          {:else if gitHubInstallations.length === 0}
            <div class="py-6 border border-dashed border-slate-800 rounded-lg text-center text-xs text-slate-500">
              No GitHub App installations connected to this workspace yet. Click "Install / Connect App" to authorize access.
            </div>
          {:else}
            <div class="divide-y divide-slate-800/60 border border-slate-800/80 rounded-lg overflow-hidden bg-slate-950/40">
              {#each gitHubInstallations as inst (inst.id)}
                <div class="p-3.5 flex items-center justify-between gap-4">
                  <div class="min-w-0">
                    <div class="flex items-center gap-2">
                      <span class="font-medium text-xs text-white">{inst.account_login}</span>
                      <span class="px-1.5 py-0.2 rounded text-[10px] font-mono bg-slate-800 text-slate-400 border border-slate-700">
                        {inst.account_type}
                      </span>
                    </div>
                    <div class="text-[11px] text-slate-500 font-mono mt-0.5">
                      Installation ID: {inst.installation_id} &bull; Installed by: @{inst.installer_github_user_login}
                    </div>
                  </div>

                  {#if selectedWsDetail.role === "owner" || selectedWsDetail.role === "admin"}
                    <button
                      on:click={() => handleDisconnectGitHub(inst.id, inst.account_login)}
                      class="text-xs text-rose-400 hover:text-rose-300 font-medium transition-colors"
                    >
                      Disconnect
                    </button>
                  {/if}
                </div>
              {/each}
            </div>
          {/if}
        </div>
      {:else}
        <div class="rounded-xl border border-slate-800 bg-slate-900/30 p-12 text-center text-slate-400 text-xs">
          Select or create a workspace to view configuration and team members.
        </div>
      {/if}
    </div>
  </div>
</div>

<!-- Modal: GitHub Repository Picker -->
{#if selectedWsDetail}
  <RepositoryPickerModal
    workspaceId={selectedWsDetail.id}
    isOpen={showRepoPickerModal}
    on:close={() => (showRepoPickerModal = false)}
    on:attached={(e) => {
      actionMessage = `Repository "${e.detail.name}" attached successfully!`;
    }}
  />
{/if}

<!-- Modal: Create Workspace -->
{#if showCreateModal}
  <div class="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
    <div class="w-full max-w-md bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-2xl space-y-4">
      <h3 class="text-base font-bold text-white">Create New Workspace</h3>
      <form on:submit|preventDefault={handleCreateWorkspace} class="space-y-4">
        <div class="space-y-1">
          <label for="wsName" class="text-xs font-medium text-slate-300">Workspace Name</label>
          <input
            id="wsName"
            type="text"
            bind:value={newWorkspaceName}
            placeholder="e.g. Acme Engineering"
            required
            class="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-cyan-500"
          />
        </div>
        <div class="flex justify-end gap-3 pt-2">
          <button
            type="button"
            on:click={() => { showCreateModal = false; }}
            class="px-3 py-2 text-xs rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={isCreating}
            class="px-4 py-2 text-xs rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white font-medium disabled:opacity-50"
          >
            {isCreating ? "Creating..." : "Create Workspace"}
          </button>
        </div>
      </form>
    </div>
  </div>
{/if}

<!-- Modal: Rename Workspace -->
{#if showRenameModal}
  <div class="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
    <div class="w-full max-w-md bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-2xl space-y-4">
      <h3 class="text-base font-bold text-white">Rename Workspace</h3>
      <form on:submit|preventDefault={handleRenameWorkspace} class="space-y-4">
        <div class="space-y-1">
          <label for="renameWs" class="text-xs font-medium text-slate-300">New Name</label>
          <input
            id="renameWs"
            type="text"
            bind:value={renameWorkspaceName}
            required
            class="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-sm text-slate-100 focus:outline-none focus:border-cyan-500"
          />
        </div>
        <div class="flex justify-end gap-3 pt-2">
          <button
            type="button"
            on:click={() => { showRenameModal = false; }}
            class="px-3 py-2 text-xs rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={isRenaming}
            class="px-4 py-2 text-xs rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white font-medium disabled:opacity-50"
          >
            {isRenaming ? "Saving..." : "Save Changes"}
          </button>
        </div>
      </form>
    </div>
  </div>
{/if}

<!-- Modal: Add Member -->
{#if showAddMemberModal}
  <div class="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
    <div class="w-full max-w-md bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-2xl space-y-4">
      <div>
        <h3 class="text-base font-bold text-white">Add Team Member</h3>
        <p class="text-xs text-slate-400 mt-1">
          Add an existing registered DevVision AI user to this workspace by email.
        </p>
      </div>
      <form on:submit|preventDefault={handleAddMember} class="space-y-4">
        <div class="space-y-1">
          <label for="memberEmail" class="text-xs font-medium text-slate-300">Registered User Email</label>
          <input
            id="memberEmail"
            type="email"
            bind:value={newMemberEmail}
            placeholder="colleague@example.com"
            required
            class="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-cyan-500"
          />
        </div>
        <div class="space-y-1">
          <label for="memberRole" class="text-xs font-medium text-slate-300">Workspace Role</label>
          <select
            id="memberRole"
            bind:value={newMemberRole}
            class="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-sm text-slate-100 focus:outline-none focus:border-cyan-500"
          >
            <option value="member">Member (read/write workspace resources)</option>
            <option value="admin">Admin (manage members & workspace settings)</option>
          </select>
        </div>
        <div class="flex justify-end gap-3 pt-2">
          <button
            type="button"
            on:click={() => { showAddMemberModal = false; }}
            class="px-3 py-2 text-xs rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={isAddingMember}
            class="px-4 py-2 text-xs rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white font-medium disabled:opacity-50"
          >
            {isAddingMember ? "Adding..." : "Add Member"}
          </button>
        </div>
      </form>
    </div>
  </div>
{/if}

<!-- Modal: Transfer Ownership -->
{#if showTransferModal}
  <div class="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
    <div class="w-full max-w-md bg-slate-900 border border-amber-800/60 rounded-xl p-6 shadow-2xl space-y-4">
      <div>
        <h3 class="text-base font-bold text-amber-300">Transfer Workspace Ownership</h3>
        <p class="text-xs text-slate-400 mt-1">
          Warning: Transferring ownership will make the recipient the sole owner of this workspace. Your role will be changed to Admin.
        </p>
      </div>
      <form on:submit|preventDefault={handleTransferOwnership} class="space-y-4">
        <div class="space-y-1">
          <label for="newOwner" class="text-xs font-medium text-slate-300">Select New Owner</label>
          <select
            id="newOwner"
            bind:value={newOwnerUserId}
            required
            class="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-sm text-slate-100 focus:outline-none focus:border-amber-500"
          >
            <option value="" disabled selected>Select an active workspace member...</option>
            {#each membersList.filter((m) => m.role !== 'owner') as eligible (eligible.user_id)}
              <option value={eligible.user_id}>
                {eligible.display_name} ({eligible.email}) - {eligible.role}
              </option>
            {/each}
          </select>
        </div>
        <div class="flex justify-end gap-3 pt-2">
          <button
            type="button"
            on:click={() => { showTransferModal = false; }}
            class="px-3 py-2 text-xs rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={isTransferring || !newOwnerUserId}
            class="px-4 py-2 text-xs rounded-lg bg-amber-600 hover:bg-amber-500 text-white font-medium disabled:opacity-50"
          >
            {isTransferring ? "Transferring..." : "Confirm Transfer"}
          </button>
        </div>
      </form>
    </div>
  </div>
{/if}
