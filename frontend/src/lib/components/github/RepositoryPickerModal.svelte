<script lang="ts">
  import { createEventDispatcher } from "svelte";
  import { api } from "$lib/api/client";
  import type { GitHubDiscoveredRepo } from "$lib/api/types";

  export let workspaceId: string;
  export let isOpen: boolean = false;

  const dispatch = createEventDispatcher<{
    attached: { repoId: number; name: string };
    close: void;
  }>();

  let repos: GitHubDiscoveredRepo[] = [];
  let isLoading = false;
  let isAttachingId: number | null = null;
  let errorMsg = "";
  let successMsg = "";
  let searchQuery = "";

  $: if (isOpen && workspaceId) {
    loadDiscoveredRepos();
  }

  async function loadDiscoveredRepos() {
    isLoading = true;
    errorMsg = "";
    successMsg = "";
    const res = await api.discoverGitHubRepositories(workspaceId);
    isLoading = false;

    if (res.success && res.data) {
      repos = res.data.items;
    } else {
      errorMsg = res.error || "Failed to load GitHub repositories.";
    }
  }

  async function handleAttach(repo: GitHubDiscoveredRepo) {
    if (repo.is_archived || repo.attachment_status !== "unattached") return;
    isAttachingId = repo.github_repo_id;
    errorMsg = "";
    successMsg = "";

    const res = await api.attachGitHubRepository(workspaceId, repo.github_repo_id);
    isAttachingId = null;

    if (res.success && res.data) {
      successMsg = `Repository ${repo.full_name} attached successfully!`;
      dispatch("attached", { repoId: repo.github_repo_id, name: repo.name });
      // Update local status
      repos = repos.map((r) =>
        r.github_repo_id === repo.github_repo_id
          ? { ...r, attachment_status: "attached_to_this_workspace" }
          : r
      );
    } else {
      errorMsg = res.error || "Failed to attach repository.";
    }
  }

  function handleClose() {
    errorMsg = "";
    successMsg = "";
    searchQuery = "";
    dispatch("close");
  }

  $: filteredRepos = repos.filter((r) => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    return (
      r.name.toLowerCase().includes(q) ||
      r.full_name.toLowerCase().includes(q) ||
      r.installation_account.toLowerCase().includes(q)
    );
  });
</script>

{#if isOpen}
  <div class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm">
    <div class="bg-slate-900 border border-slate-800 rounded-xl shadow-2xl max-w-2xl w-full flex flex-col max-h-[85vh] overflow-hidden">
      <!-- Modal Header -->
      <div class="p-5 border-b border-slate-800 flex items-center justify-between">
        <div class="flex items-center gap-3">
          <div class="p-2 rounded-lg bg-slate-800 text-slate-200">
            <svg class="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
              <path fill-rule="evenodd" clip-rule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" />
            </svg>
          </div>
          <div>
            <h3 class="text-base font-semibold text-white">Attach GitHub Repository</h3>
            <p class="text-xs text-slate-400">Discover and link repositories accessible to your installed GitHub App</p>
          </div>
        </div>
        <button
          on:click={handleClose}
          class="text-slate-400 hover:text-white p-1 rounded-lg transition-colors"
          aria-label="Close modal"
        >
          ✕
        </button>
      </div>

      <!-- Search & Filters -->
      <div class="p-4 border-b border-slate-800 bg-slate-900/40">
        <input
          type="text"
          bind:value={searchQuery}
          placeholder="Filter by repo name, organization, or owner..."
          class="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500"
        />
      </div>

      <!-- Feedback Alerts -->
      {#if errorMsg}
        <div class="mx-4 mt-3 p-3 rounded-lg bg-rose-950/80 border border-rose-800 text-rose-300 text-xs">
          {errorMsg}
        </div>
      {/if}
      {#if successMsg}
        <div class="mx-4 mt-3 p-3 rounded-lg bg-emerald-950/80 border border-emerald-800 text-emerald-300 text-xs">
          {successMsg}
        </div>
      {/if}

      <!-- Repositories List -->
      <div class="p-4 overflow-y-auto flex-1 divide-y divide-slate-800/60">
        {#if isLoading}
          <div class="py-12 flex flex-col items-center justify-center gap-3 text-slate-400">
            <div class="animate-spin rounded-full h-6 w-6 border-b-2 border-cyan-500"></div>
            <span class="text-xs font-mono">Querying GitHub App installations...</span>
          </div>
        {:else if filteredRepos.length === 0}
          <div class="py-12 text-center text-slate-500 text-xs font-mono">
            {#if repos.length === 0}
              No repositories discovered. Please ensure your GitHub App is installed on an organization or personal account with repository access permissions.
            {:else}
              No repositories match your filter query.
            {/if}
          </div>
        {:else}
          {#each filteredRepos as repo (repo.github_repo_id)}
            <div class="py-3 flex items-center justify-between gap-4">
              <div class="min-w-0 flex-1">
                <div class="flex items-center gap-2">
                  <span class="font-medium text-xs text-white truncate">{repo.full_name}</span>
                  {#if repo.is_private}
                    <span class="px-1.5 py-0.2 rounded text-[10px] font-mono bg-slate-800 text-slate-400 border border-slate-700">
                      Private
                    </span>
                  {:else}
                    <span class="px-1.5 py-0.2 rounded text-[10px] font-mono bg-cyan-950/80 text-cyan-400 border border-cyan-800">
                      Public
                    </span>
                  {/if}
                  {#if repo.is_archived}
                    <span class="px-1.5 py-0.2 rounded text-[10px] font-mono bg-amber-950/80 text-amber-400 border border-amber-800">
                      Archived
                    </span>
                  {/if}
                </div>
                <div class="text-[11px] text-slate-500 font-mono mt-0.5">
                  Default branch: <span class="text-slate-300">{repo.default_branch}</span> &bull;
                  Account: <span class="text-slate-400">{repo.installation_account}</span>
                </div>
              </div>

              <div>
                {#if repo.attachment_status === "attached_to_this_workspace"}
                  <span class="inline-flex items-center gap-1.5 text-xs text-emerald-400 bg-emerald-950/50 border border-emerald-800/80 px-2.5 py-1 rounded-lg">
                    <span>✓</span> Attached
                  </span>
                {:else if repo.attachment_status === "unavailable"}
                  <span class="inline-flex items-center text-xs text-slate-500 bg-slate-800/60 px-2.5 py-1 rounded-lg" title="Attached to another workspace or globally unavailable">
                    Unavailable
                  </span>
                {:else if repo.is_archived}
                  <span class="inline-flex items-center text-xs text-slate-500 bg-slate-800/60 px-2.5 py-1 rounded-lg">
                    Archived (Read-Only)
                  </span>
                {:else}
                  <button
                    on:click={() => handleAttach(repo)}
                    disabled={isAttachingId === repo.github_repo_id}
                    class="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white transition-all shadow-sm"
                  >
                    {#if isAttachingId === repo.github_repo_id}
                      <span class="animate-spin rounded-full h-3 w-3 border-b-2 border-white"></span>
                      Attaching...
                    {:else}
                      Attach Repo
                    {/if}
                  </button>
                {/if}
              </div>
            </div>
          {/each}
        {/if}
      </div>

      <!-- Modal Footer -->
      <div class="p-4 border-t border-slate-800 bg-slate-900/60 flex items-center justify-between">
        <span class="text-[11px] text-slate-400 font-mono">
          Only organization admins or personal owners can attach repositories.
        </span>
        <button
          on:click={handleClose}
          class="px-4 py-1.5 rounded-lg border border-slate-700 bg-slate-800 hover:bg-slate-700 text-xs text-slate-200 transition-colors"
        >
          Close
        </button>
      </div>
    </div>
  </div>
{/if}