<script lang="ts">
  import { currentUser } from "$lib/stores/auth";
  import { activeWorkspace, workspaces } from "$lib/stores/workspace";
</script>

<div class="space-y-8">
  <!-- Welcome Banner -->
  <div class="rounded-xl border border-slate-800 bg-gradient-to-b from-slate-900/60 to-slate-950 p-6 md:p-8 shadow-xl">
    <div class="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
      <div>
        <div class="inline-flex items-center gap-2 px-2.5 py-1 rounded-full bg-cyan-950/80 border border-cyan-800/60 text-cyan-300 text-xs font-medium mb-3">
          <span class="h-1.5 w-1.5 rounded-full bg-cyan-400 animate-pulse"></span>
          Phase 1: Multi-Tenant Foundation
        </div>
        <h1 class="text-2xl md:text-3xl font-bold tracking-tight text-white">
          Welcome, {$currentUser?.display_name || "Developer"}
        </h1>
        <p class="text-sm text-slate-400 mt-1 max-w-2xl">
          You are authenticated with PostgreSQL-backed opaque sessions and explicit CSRF protection. Workspaces define your tenant isolation boundary.
        </p>
      </div>

      <div class="flex items-center gap-3">
        <a
          href="/documents"
          class="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white transition-all shadow-md shadow-cyan-600/20 active:scale-95"
        >
          Manage Documents &rarr;
        </a>
        <a
          href="/workspaces"
          class="inline-flex items-center gap-2 px-3 py-2 text-sm font-medium rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition-all border border-slate-700"
        >
          Workspaces
        </a>
      </div>
    </div>
  </div>

  <!-- Active Workspace Status Card -->
  {#if $activeWorkspace}
    <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
      <div class="rounded-lg border border-slate-800 bg-slate-900/50 p-5 space-y-2">
        <span class="text-xs font-semibold uppercase tracking-wider text-slate-400">Active Workspace</span>
        <div class="text-xl font-bold text-white truncate">{$activeWorkspace.name}</div>
        <p class="text-xs font-mono text-slate-500 truncate">slug: {$activeWorkspace.slug}</p>
        <p class="text-[11px] font-mono text-slate-600 truncate">ID: {$activeWorkspace.id}</p>
      </div>

      <div class="rounded-lg border border-slate-800 bg-slate-900/50 p-5 space-y-2">
        <span class="text-xs font-semibold uppercase tracking-wider text-slate-400">Your Role</span>
        <div class="text-xl font-bold text-cyan-400 capitalize">{$activeWorkspace.role}</div>
        <p class="text-xs text-slate-400">
          {#if $activeWorkspace.role === "owner"}
            Full administrative control, billing, member management & ownership transfer.
          {:else if $activeWorkspace.role === "admin"}
            Can manage workspace members and settings. Cannot delete or transfer ownership.
          {:else}
            Standard member access to workspace projects and resources.
          {/if}
        </p>
      </div>

      <div class="rounded-lg border border-slate-800 bg-slate-900/50 p-5 space-y-2">
        <span class="text-xs font-semibold uppercase tracking-wider text-slate-400">Total Workspaces</span>
        <div class="text-xl font-bold text-white">{$workspaces.length}</div>
        <p class="text-xs text-slate-400">
          Workspaces you own or belong to across the platform.
        </p>
      </div>
    </div>
  {:else}
    <div class="rounded-xl border border-slate-800 bg-slate-900/40 p-8 text-center space-y-4">
      <div class="h-12 w-12 rounded-full bg-slate-800 text-slate-400 flex items-center justify-center mx-auto text-xl">
        🏢
      </div>
      <h3 class="text-lg font-semibold text-white">No Active Workspace Selected</h3>
      <p class="text-xs text-slate-400 max-w-md mx-auto">
        You do not currently have an active workspace selected. Create a new workspace to start organizing your projects and team.
      </p>
      <a
        href="/workspaces"
        class="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white transition-all shadow-md shadow-cyan-600/20"
      >
        Go to Workspace Management
      </a>
    </div>
  {/if}

  <!-- Security & Architecture Summary -->
  <div class="rounded-xl border border-slate-800 bg-slate-900/30 p-6 space-y-4">
    <h3 class="text-sm font-semibold text-white tracking-tight">Phase 1 Active Security Controls</h3>
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 text-xs">
      <div class="p-4 rounded-lg bg-slate-950/60 border border-slate-800/80 space-y-2">
        <div class="flex items-center gap-2 font-medium text-cyan-400">
          <span class="h-2 w-2 rounded-full bg-emerald-400"></span>
          Opaque Server Sessions
        </div>
        <p class="text-slate-400 leading-relaxed">
          SHA-256 hashed 32-byte tokens stored in PostgreSQL. Raw session token transmitted solely via HttpOnly, SameSite=Lax cookie.
        </p>
      </div>

      <div class="p-4 rounded-lg bg-slate-950/60 border border-slate-800/80 space-y-2">
        <div class="flex items-center gap-2 font-medium text-cyan-400">
          <span class="h-2 w-2 rounded-full bg-emerald-400"></span>
          Explicit Double-Submit CSRF
        </div>
        <p class="text-slate-400 leading-relaxed">
          Synchronizer token issued in separate devvision_csrf cookie; verified via constant-time hmac.compare_digest on state changes.
        </p>
      </div>

      <div class="p-4 rounded-lg bg-slate-950/60 border border-slate-800/80 space-y-2">
        <div class="flex items-center gap-2 font-medium text-cyan-400">
          <span class="h-2 w-2 rounded-full bg-emerald-400"></span>
          RBAC & Tenant Isolation
        </div>
        <p class="text-slate-400 leading-relaxed">
          All queries filtered by workspace membership. Non-members receive generic 404 to prevent IDOR workspace enumeration.
        </p>
      </div>
    </div>
  </div>
</div>
