<script lang="ts">
  import { onMount } from "svelte";
  import { goto } from "$app/navigation";
  import { currentUser, isAuthLoading, refreshCurrentUser } from "$lib/stores/auth";
  import { workspaces, activeWorkspace, fetchWorkspaces, setActiveWorkspace } from "$lib/stores/workspace";
  import { api } from "$lib/api/client";

  let isLoggingOut = false;

  onMount(async () => {
    const user = await refreshCurrentUser();
    if (!user) {
      goto("/login");
      return;
    }
    await fetchWorkspaces();
  });

  async function handleLogout() {
    isLoggingOut = true;
    try {
      await api.logout();
    } finally {
      currentUser.set(null);
      isLoggingOut = false;
      goto("/login");
    }
  }

  function onWorkspaceChange(event: Event) {
    const select = event.target as HTMLSelectElement;
    const selected = $workspaces.find ((w) => w.id === select.value);
    if (selected) {
      setActiveWorkspace(selected);
    }
  }
</script>

<div class="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
  <!-- Top App Navigation Bar -->
  <header class="sticky top-0 z-50 border-b border-slate-800/80 bg-slate-950/80 backdrop-blur-md px-6 py-3 flex items-center justify-between">
    <div class="flex items-center gap-6">
      <a href="/app" class="flex items-center gap-3 group">
        <div class="h-8 w-8 rounded-lg bg-gradient-to-tr from-cyan-500 to-blue-600 flex items-center justify-center font-bold text-white shadow-md shadow-cyan-500/20 group-hover:scale-105 transition-transform">
          DV
        </div>
        <div>
          <div class="flex items-center gap-2">
            <span class="font-semibold tracking-tight text-white text-sm">DevVision AI</span>
            <span class="text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-cyan-950/80 text-cyan-400 border border-cyan-800/50">
              Phase 3
            </span>
          </div>
        </div>
      </a>

      <!-- Workspace Selector -->
      {#if $workspaces.length > 0}
        <div class="flex items-center gap-2 pl-4 border-l border-slate-800">
          <span class="text-xs text-slate-400 hidden sm:inline">Workspace:</span>
          <select
            value={$activeWorkspace?.id || ""}
            on:change={onWorkspaceChange}
            class="bg-slate-900 border border-slate-700/80 text-xs text-slate-200 rounded-lg px-2.5 py-1.5 focus:outline-none focus:border-cyan-500 transition-colors"
          >
            {#each $workspaces as ws (ws.id)}
              <option value={ws.id}>
                {ws.name} ({ws.role})
              </option>
            {/each}
          </select>
        </div>
      {/if}
    </div>

    <!-- Right Side Actions & User Menu -->
    <div class="flex items-center gap-4 text-xs">
      <nav class="flex items-center gap-3 text-slate-300">
        <a href="/app" class="hover:text-cyan-400 transition-colors">Dashboard</a>
        <a href="/workspaces" class="hover:text-cyan-400 transition-colors">Workspaces</a>
        <a href="/documents" class="hover:text-cyan-400 transition-colors">Documents</a>
        <a href="/rag" class="hover:text-cyan-400 transition-colors">RAG Assistant</a>
        <a href="/" class="text-slate-400 hover:text-slate-200 transition-colors">Diagnostics</a>
      </nav>

      <div class="flex items-center gap-3 pl-4 border-l border-slate-800">
        {#if $currentUser}
          <div class="flex items-center gap-2">
            <div class="h-7 w-7 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center font-semibold text-slate-300 uppercase text-xs">
              {$currentUser.display_name ? $currentUser.display_name[0] : $currentUser.email[0]}
            </div>
            <div class="hidden md:block text-left">
              <div class="text-xs font-medium text-slate-200">{$currentUser.display_name}</div>
              <div class="text-[11px] text-slate-400 truncate max-w-[140px]">{$currentUser.email}</div>
            </div>
          </div>
        {/if}

        <button
          on:click={handleLogout}
          disabled={isLoggingOut}
          class="px-2.5 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 text-slate-300 hover:text-rose-400 border border-slate-800 text-xs transition-colors disabled:opacity-50"
          title="Sign out of your session"
        >
          {isLoggingOut ? "Signing out..." : "Sign Out"}
        </button>
      </div>
    </div>
  </header>

  <!-- Dashboard Body -->
  <main class="flex-1 max-w-7xl w-full mx-auto p-6 md:p-8">
    {#if $isAuthLoading}
      <div class="flex flex-col items-center justify-center min-h-[50vh] space-y-4">
        <div class="h-8 w-8 border-2 border-cyan-500 border-t-transparent rounded-full animate-spin"></div>
        <p class="text-xs text-slate-400">Verifying authentication & loading workspaces...</p>
      </div>
    {:else}
      <slot />
    {/if}
  </main>
</div>