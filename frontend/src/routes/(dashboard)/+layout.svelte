<script lang="ts">
  import { onMount } from "svelte";
  import { goto } from "$app/navigation";
  import { page } from "$app/stores";
  import { currentUser, isAuthLoading, refreshCurrentUser } from "$lib/stores/auth";
  import { workspaces, activeWorkspace, fetchWorkspaces, setActiveWorkspace } from "$lib/stores/workspace";
  import { api } from "$lib/api/client";
  import {
    LayoutDashboard,
    Folders,
    FileText,
    Bot,
    GitBranch,
    Shield,
    Activity,
    LogOut,
    ChevronDown,
    Plus,
    ExternalLink,
    Terminal,
    Sparkles,
    UserCheck,
    Lock
  } from "lucide-svelte";

  let isLoggingOut = false;
  let showUserMenu = false;
  let showWsMenu = false;

  $: pathname = $page.url.pathname;

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

  function selectWorkspace(ws: any) {
    setActiveWorkspace(ws);
    showWsMenu = false;
  }
</script>

<svelte:window on:click={() => { showUserMenu = false; showWsMenu = false; }} />

<div class="min-h-screen bg-[#090d16] text-slate-100 flex flex-col font-sans antialiased selection:bg-cyan-500 selection:text-white">
  <!-- Top Universal Header -->
  <header class="sticky top-0 z-40 border-b border-slate-800/80 bg-[#090d16]/90 backdrop-blur-md px-4 sm:px-6 h-14 flex items-center justify-between">
    <div class="flex items-center gap-4 sm:gap-6">
      <!-- App Brand -->
      <a href="/app" class="flex items-center gap-2.5 group">
        <div class="h-8 w-8 rounded-lg bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center font-mono font-bold text-white text-xs shadow-sm shadow-cyan-500/30 group-hover:scale-[1.02] transition-transform">
          DV
        </div>
        <div class="flex items-center gap-2">
          <span class="font-semibold text-sm tracking-tight text-white group-hover:text-cyan-300 transition-colors">DevVision</span>
          <span class="text-[10px] font-mono uppercase tracking-wider px-1.5 py-0.5 rounded bg-cyan-950/80 text-cyan-400 border border-cyan-800/60 hidden sm:inline">
            v1.0
          </span>
        </div>
      </a>

      <!-- Workspace Switcher Dropdown -->
      {#if $workspaces.length > 0}
        <div class="relative">
          <button
            type="button"
            on:click|stopPropagation={() => { showWsMenu = !showWsMenu; showUserMenu = false; }}
            class="flex items-center gap-2 px-2.5 py-1.5 rounded-md bg-slate-900/90 border border-slate-800 hover:border-slate-700 text-xs text-slate-200 transition-colors"
          >
            <Folders class="w-3.5 h-3.5 text-cyan-400" />
            <span class="max-w-[130px] truncate font-medium">{$activeWorkspace?.name || "Select Workspace"}</span>
            {#if $activeWorkspace?.role}
              <span class="text-[10px] px-1.5 py-0.2 rounded bg-slate-800 text-slate-400 border border-slate-700/60 capitalize font-mono">
                {$activeWorkspace.role}
              </span>
            {/if}
            <ChevronDown class="w-3 h-3 text-slate-400 ml-0.5" />
          </button>

          {#if showWsMenu}
            <div on:keydown|stopPropagation class="absolute left-0 mt-1.5 w-60 rounded-lg bg-slate-900 border border-slate-800 shadow-xl py-1 z-50 animate-in fade-in zoom-in-95 duration-100" role="menu" tabindex="-1">
              <div class="px-3 py-1.5 text-[11px] font-medium uppercase tracking-wider text-slate-400 border-b border-slate-800/80">
                Workspaces ({$workspaces.length})
              </div>
              <div class="max-h-60 overflow-y-auto py-1">
                {#each $workspaces as ws}
                  <button
                    type="button"
                    on:click={() => selectWorkspace(ws)}
                    class="w-full text-left px-3 py-2 text-xs flex items-center justify-between hover:bg-slate-800/70 transition-colors {ws.id === $activeWorkspace?.id ? 'text-cyan-400 font-medium bg-slate-800/40' : 'text-slate-300'}"
                  >
                    <span class="truncate">{ws.name}</span>
                    <span class="text-[10px] font-mono uppercase text-slate-400">{ws.role}</span>
                  </button>
                {/each}
              </div>
              <div class="border-t border-slate-800/80 p-1.5">
                <a
                  href="/workspaces"
                  on:click={() => (showWsMenu = false)}
                  class="flex items-center gap-1.5 text-xs text-slate-300 hover:text-white px-2 py-1.5 rounded hover:bg-slate-800/60 transition-colors"
                >
                  <Plus class="w-3.5 h-3.5 text-cyan-400" />
                  <span>Manage / Create Workspace</span>
                </a>
              </div>
            </div>
          {/if}
        </div>
      {/if}
    </div>

    <!-- Navigation Tabs -->
    <nav class="hidden lg:flex items-center gap-1 text-xs">
      <a
        href="/app"
        class="flex items-center gap-1.5 px-3 py-1.5 rounded-md font-medium transition-colors {pathname === '/app' ? 'bg-slate-800/90 text-cyan-300 shadow-sm' : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/60'}"
      >
        <LayoutDashboard class="w-3.5 h-3.5" />
        <span>Dashboard</span>
      </a>
      <a
        href="/codebases"
        class="flex items-center gap-1.5 px-3 py-1.5 rounded-md font-medium transition-colors {pathname.startsWith('/codebases') ? 'bg-slate-800/90 text-cyan-300 shadow-sm' : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/60'}"
      >
        <GitBranch class="w-3.5 h-3.5" />
        <span>Codebases</span>
      </a>
      <a
        href="/rag"
        class="flex items-center gap-1.5 px-3 py-1.5 rounded-md font-medium transition-colors {pathname === '/rag' ? 'bg-slate-800/90 text-cyan-300 shadow-sm' : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/60'}"
      >
        <Bot class="w-3.5 h-3.5" />
        <span>RAG Copilot</span>
      </a>
      <a
        href="/documents"
        class="flex items-center gap-1.5 px-3 py-1.5 rounded-md font-medium transition-colors {pathname === '/documents' ? 'bg-slate-800/90 text-cyan-300 shadow-sm' : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/60'}"
      >
        <FileText class="w-3.5 h-3.5" />
        <span>Documents</span>
      </a>
      <a
        href="/workspaces"
        class="flex items-center gap-1.5 px-3 py-1.5 rounded-md font-medium transition-colors {pathname === '/workspaces' ? 'bg-slate-800/90 text-cyan-300 shadow-sm' : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/60'}"
      >
        <Folders class="w-3.5 h-3.5" />
        <span>Workspaces</span>
      </a>
      <a
        href="/admin"
        class="flex items-center gap-1.5 px-3 py-1.5 rounded-md font-medium transition-colors {pathname === '/admin' ? 'bg-slate-800/90 text-cyan-300 shadow-sm' : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/60'}"
      >
        <Shield class="w-3.5 h-3.5" />
        <span>Admin Control</span>
      </a>
    </nav>

    <!-- User Profile & Action Menu -->
    <div class="flex items-center gap-3 text-xs">
      <a
        href="/"
        class="hidden sm:inline-flex items-center gap-1 text-[11px] font-mono text-slate-400 hover:text-cyan-300 transition-colors px-2 py-1 rounded bg-slate-900/80 border border-slate-800"
      >
        <Activity class="w-3 h-3 text-emerald-400" />
        <span>Cluster Health</span>
      </a>

      {#if $currentUser}
        <div class="relative">
          <button
            type="button"
            on:click|stopPropagation={() => { showUserMenu = !showUserMenu; showWsMenu = false; }}
            class="flex items-center gap-2 p-1 pl-1.5 pr-2 rounded-full bg-slate-900 border border-slate-800 hover:border-slate-700 transition-colors"
          >
            <div class="h-6 w-6 rounded-full bg-gradient-to-tr from-cyan-600 to-blue-600 text-white font-mono font-bold flex items-center justify-center text-[10px]">
              {$currentUser.display_name ? $currentUser.display_name[0].toUpperCase() : $currentUser.email[0].toUpperCase()}
            </div>
            <span class="max-w-[110px] truncate text-slate-300 font-medium text-xs hidden md:inline">
              {$currentUser.display_name || $currentUser.email.split("@")[0]}
            </span>
            <ChevronDown class="w-3 h-3 text-slate-400" />
          </button>

          {#if showUserMenu}
            <div on:keydown|stopPropagation class="absolute right-0 mt-2 w-56 rounded-lg bg-slate-900 border border-slate-800 shadow-2xl py-1.5 z-50 animate-in fade-in zoom-in-95 duration-100" role="menu" tabindex="-1">
              <div class="px-3.5 py-2 border-b border-slate-800/80">
                <div class="text-xs font-semibold text-white truncate">{$currentUser.display_name}</div>
                <div class="text-[11px] text-slate-400 font-mono truncate">{$currentUser.email}</div>
              </div>
              <div class="py-1 text-xs">
                <a
                  href="/app"
                  on:click={() => (showUserMenu = false)}
                  class="flex items-center gap-2 px-3.5 py-1.5 text-slate-300 hover:text-white hover:bg-slate-800/60 transition-colors"
                >
                  <LayoutDashboard class="w-3.5 h-3.5 text-slate-400" />
                  <span>Overview</span>
                </a>
                <a
                  href="/admin"
                  on:click={() => (showUserMenu = false)}
                  class="flex items-center gap-2 px-3.5 py-1.5 text-slate-300 hover:text-white hover:bg-slate-800/60 transition-colors"
                >
                  <Shield class="w-3.5 h-3.5 text-slate-400" />
                  <span>Admin & Governance</span>
                </a>
                <a
                  href="/workspaces"
                  on:click={() => (showUserMenu = false)}
                  class="flex items-center gap-2 px-3.5 py-1.5 text-slate-300 hover:text-white hover:bg-slate-800/60 transition-colors"
                >
                  <Folders class="w-3.5 h-3.5 text-slate-400" />
                  <span>Workspaces</span>
                </a>
              </div>
              <div class="border-t border-slate-800/80 pt-1">
                <button
                  type="button"
                  on:click={handleLogout}
                  disabled={isLoggingOut}
                  class="w-full text-left flex items-center gap-2 px-3.5 py-1.5 text-xs text-rose-400 hover:bg-rose-950/40 hover:text-rose-300 transition-colors"
                >
                  <LogOut class="w-3.5 h-3.5" />
                  <span>{isLoggingOut ? "Signing out..." : "Sign Out"}</span>
                </button>
              </div>
            </div>
          {/if}
        </div>
      {:else}
        <a
          href="/login"
          class="px-3 py-1.5 rounded-md bg-cyan-600 hover:bg-cyan-500 text-white font-medium text-xs transition-colors shadow-sm shadow-cyan-600/20"
        >
          Sign In
        </a>
      {/if}
    </div>
  </header>

  <!-- Mobile Sub-Navigation -->
  <div class="lg:hidden flex items-center gap-2 px-4 py-2 border-b border-slate-800/80 bg-[#090d16] overflow-x-auto text-xs scrollbar-none">
    <a href="/app" class="px-2.5 py-1 rounded-md {pathname === '/app' ? 'bg-slate-800 text-cyan-300' : 'text-slate-400'}">Dashboard</a>
    <a href="/codebases" class="px-2.5 py-1 rounded-md {pathname.startsWith('/codebases') ? 'bg-slate-800 text-cyan-300' : 'text-slate-400'}">Codebases</a>
    <a href="/rag" class="px-2.5 py-1 rounded-md {pathname === '/rag' ? 'bg-slate-800 text-cyan-300' : 'text-slate-400'}">RAG</a>
    <a href="/documents" class="px-2.5 py-1 rounded-md {pathname === '/documents' ? 'bg-slate-800 text-cyan-300' : 'text-slate-400'}">Docs</a>
    <a href="/workspaces" class="px-2.5 py-1 rounded-md {pathname === '/workspaces' ? 'bg-slate-800 text-cyan-300' : 'text-slate-400'}">Workspaces</a>
    <a href="/admin" class="px-2.5 py-1 rounded-md {pathname === '/admin' ? 'bg-slate-800 text-cyan-300' : 'text-slate-400'}">Admin</a>
  </div>

  <!-- Dashboard Body -->
  <main class="flex-1 max-w-7xl w-full mx-auto p-4 sm:p-6 md:p-8">
    {#if $isAuthLoading}
      <div class="flex flex-col items-center justify-center min-h-[60vh] space-y-4">
        <div class="h-7 w-7 border-2 border-cyan-500 border-t-transparent rounded-full animate-spin"></div>
        <p class="text-xs text-slate-400 font-mono">Authenticating secure session...</p>
      </div>
    {:else}
      <slot />
    {/if}
  </main>

  <!-- Minimal Dev Footer -->
  <footer class="border-t border-slate-800/60 py-4 px-6 text-slate-500 text-[11px] flex flex-col sm:flex-row items-center justify-between gap-2">
    <div class="flex items-center gap-2">
      <span class="h-1.5 w-1.5 rounded-full bg-emerald-400"></span>
      <span>DevVision AI Modular Monolith</span>
      <span>•</span>
      <span class="font-mono">Self-Hosted Only</span>
    </div>
    <div class="flex items-center gap-4">
      <a href="/admin" class="hover:text-slate-400 transition-colors">Admin Controls</a>
      <a href="/" class="hover:text-slate-400 transition-colors">System Health</a>
      <a href="https://github.com/Eshwar187/dev_vision" target="_blank" rel="noreferrer" class="hover:text-slate-400 transition-colors flex items-center gap-1">
        <span>GitHub</span>
        <ExternalLink class="w-3 h-3" />
      </a>
    </div>
  </footer>
</div>