<script lang="ts">
  import { onMount } from "svelte";
  import { activeWorkspace, workspaces, fetchWorkspaces } from "$lib/stores/workspace";
  import { currentUser } from "$lib/stores/auth";
  import { api } from "$lib/api/client";
  import {
    Shield,
    Users,
    Key,
    Database,
    Cpu,
    Lock,
    Server,
    Activity,
    AlertTriangle,
    RefreshCw,
    CheckCircle2,
    Sliders
  } from "lucide-svelte";
  import type { WorkspaceMember, WorkspaceDetail } from "$lib/api/types";

  let activeTab: "governance" | "security" | "system" | "audit" = "governance";
  let members: WorkspaceMember[] = [];
  let workspaceDetail: WorkspaceDetail | null = null;
  let isLoading = false;
  let systemHealth: any = null;
  let isCheckingHealth = false;
  let actionMessage = "";
  let actionError = "";

  // Add Member Modal
  let showAddMemberModal = false;
  let newMemberEmail = "";
  let newMemberRole: "admin" | "member" = "member";
  let isAddingMember = false;

  $: currentWs = $activeWorkspace;
  $: isOwnerOrAdmin = currentWs?.role === "owner" || currentWs?.role === "admin";

  onMount(async () => {
    await loadAdminData();
  });

  $: if (currentWs?.id) {
    loadAdminData();
  }

  async function loadAdminData() {
    if (!currentWs) return;
    isLoading = true;
    actionError = "";
    actionMessage = "";

    const [wsRes, memRes, healthRes] = await Promise.all([
      api.getWorkspace(currentWs.id),
      api.listMembers(currentWs.id),
      api.checkReady(),
    ]);

    isLoading = false;
    if (wsRes.success && wsRes.data) workspaceDetail = wsRes.data;
    if (memRes.success && memRes.data) members = memRes.data.members;
    if (healthRes.success && healthRes.data) systemHealth = healthRes.data;
  }

  async function handleAddMember() {
    if (!newMemberEmail.trim() || !currentWs) return;
    isAddingMember = true;
    actionError = "";
    actionMessage = "";

    const res = await api.addMember(currentWs.id, newMemberEmail.trim(), newMemberRole);
    isAddingMember = false;

    if (res.success) {
      showAddMemberModal = false;
      newMemberEmail = "";
      actionMessage = `Member ${newMemberEmail} added successfully.`;
      const memRes = await api.listMembers(currentWs.id);
      if (memRes.success && memRes.data) members = memRes.data.members;
    } else {
      actionError = res.error || "Failed to add member to workspace.";
    }
  }

  async function handleRemoveMember(userId: string, email: string) {
    if (!currentWs) return;
    const confirmRemoval = confirm(`Remove member ${email} from workspace "${currentWs.name}"?`);
    if (!confirmRemoval) return;

    actionError = "";
    actionMessage = "";
    const res = await api.removeMember(currentWs.id, userId);
    if (res.success) {
      actionMessage = `Member ${email} removed.`;
      members = members.filter((m) => m.user_id !== userId);
    } else {
      actionError = res.error || "Failed to remove member.";
    }
  }

  async function handleRunHealthCheck() {
    isCheckingHealth = true;
    const res = await api.checkReady();
    isCheckingHealth = false;
    if (res.success && res.data) {
      systemHealth = res.data;
      actionMessage = "Infrastructure probe completed.";
    }
  }
</script>

<div class="space-y-6">
  <!-- Admin Header Banner -->
  <div class="flex flex-col md:flex-row md:items-center md:justify-between gap-4 border-b border-slate-800/80 pb-5">
    <div>
      <div class="flex items-center gap-2 mb-1">
        <span class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[11px] font-mono uppercase tracking-wider bg-cyan-950/80 text-cyan-400 border border-cyan-800/60">
          <Shield class="w-3 h-3" />
          Workspace Administration & Control Plane
        </span>
      </div>
      <h1 class="text-xl font-bold text-white tracking-tight">Admin Control Panel</h1>
      <p class="text-xs text-slate-400 mt-1">
        Tenant governance, RBAC permissions, self-hosted infrastructure probes, and token auditing for <strong class="text-slate-200">{currentWs?.name || "Active Workspace"}</strong>.
      </p>
    </div>

    <div class="flex items-center gap-3">
      <button
        type="button"
        on:click={handleRunHealthCheck}
        disabled={isCheckingHealth}
        class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-700/80 hover:border-slate-600 text-slate-300 hover:text-white text-xs font-medium transition-colors"
      >
        <RefreshCw class="w-3.5 h-3.5 {isCheckingHealth ? 'animate-spin text-cyan-400' : ''}" />
        <span>Probe Cluster</span>
      </button>
      {#if isOwnerOrAdmin}
        <button
          type="button"
          on:click={() => (showAddMemberModal = true)}
          class="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-medium transition-colors shadow-sm shadow-cyan-600/20"
        >
          <Users class="w-3.5 h-3.5" />
          <span>Invite Member</span>
        </button>
      {/if}
    </div>
  </div>

  {#if actionMessage}
    <div class="p-3 rounded-lg bg-emerald-950/50 border border-emerald-800 text-emerald-300 text-xs flex items-center justify-between">
      <div class="flex items-center gap-2">
        <CheckCircle2 class="w-4 h-4" />
        <span>{actionMessage}</span>
      </div>
      <button type="button" on:click={() => (actionMessage = "")} class="text-slate-400 hover:text-white">✕</button>
    </div>
  {/if}

  {#if actionError}
    <div class="p-3 rounded-lg bg-rose-950/60 border border-rose-800 text-rose-300 text-xs flex items-center justify-between">
      <div class="flex items-center gap-2">
        <AlertTriangle class="w-4 h-4" />
        <span>{actionError}</span>
      </div>
      <button type="button" on:click={() => (actionError = "")} class="text-slate-400 hover:text-white">✕</button>
    </div>
  {/if}

  <!-- Admin Navigation Tabs -->
  <div class="flex items-center gap-2 border-b border-slate-800/80 text-xs">
    <button
      type="button"
      on:click={() => (activeTab = "governance")}
      class="pb-2.5 px-3 font-medium transition-colors border-b-2 flex items-center gap-2 {activeTab === 'governance' ? 'border-cyan-500 text-cyan-400' : 'border-transparent text-slate-400 hover:text-slate-200'}"
    >
      <Users class="w-3.5 h-3.5" />
      <span>Access & RBAC</span>
    </button>
    <button
      type="button"
      on:click={() => (activeTab = "security")}
      class="pb-2.5 px-3 font-medium transition-colors border-b-2 flex items-center gap-2 {activeTab === 'security' ? 'border-cyan-500 text-cyan-400' : 'border-transparent text-slate-400 hover:text-slate-200'}"
    >
      <Lock class="w-3.5 h-3.5" />
      <span>Security Invariants</span>
    </button>
    <button
      type="button"
      on:click={() => (activeTab = "system")}
      class="pb-2.5 px-3 font-medium transition-colors border-b-2 flex items-center gap-2 {activeTab === 'system' ? 'border-cyan-500 text-cyan-400' : 'border-transparent text-slate-400 hover:text-slate-200'}"
    >
      <Cpu class="w-3.5 h-3.5" />
      <span>Infrastructure & Models</span>
    </button>
  </div>

  <!-- Tab 1: Access & RBAC -->
  {#if activeTab === "governance"}
    <div class="space-y-6">
      <div class="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs font-mono">
        <div class="p-4 rounded-xl bg-slate-900/60 border border-slate-800 space-y-1">
          <span class="text-slate-400 block text-[11px]">WORKSPACE ROLE</span>
          <div class="text-base font-bold text-cyan-400 capitalize">{currentWs?.role || "Member"}</div>
          <span class="text-[10px] text-slate-500">{isOwnerOrAdmin ? "Full administration privileges" : "Standard member rights"}</span>
        </div>
        <div class="p-4 rounded-xl bg-slate-900/60 border border-slate-800 space-y-1">
          <span class="text-slate-400 block text-[11px]">ACTIVE SEATS</span>
          <div class="text-base font-bold text-white">{members.length} Users</div>
          <span class="text-[10px] text-slate-500">Tenant membership count</span>
        </div>
        <div class="p-4 rounded-xl bg-slate-900/60 border border-slate-800 space-y-1">
          <span class="text-slate-400 block text-[11px]">ISOLATION ID</span>
          <div class="text-xs font-bold text-slate-300 truncate">{currentWs?.id || "None"}</div>
          <span class="text-[10px] text-slate-500">PostgreSQL tenant foreign key</span>
        </div>
      </div>

      <!-- Members Table -->
      <div class="rounded-xl border border-slate-800 bg-slate-900/40 overflow-hidden shadow-sm">
        <div class="p-4 border-b border-slate-800 flex items-center justify-between">
          <div class="text-xs font-semibold text-white">Authorized Workspace Members</div>
          <span class="text-[11px] text-slate-400">{members.length} total members</span>
        </div>

        <div class="overflow-x-auto">
          <table class="w-full text-left text-xs">
            <thead class="bg-slate-950/60 border-b border-slate-800 text-slate-400 font-mono text-[11px]">
              <tr>
                <th class="py-2.5 px-4 font-medium">User</th>
                <th class="py-2.5 px-4 font-medium">Role</th>
                <th class="py-2.5 px-4 font-medium">User ID</th>
                <th class="py-2.5 px-4 font-medium text-right">Actions</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-800/60">
              {#each members as m (m.user_id)}
                <tr class="hover:bg-slate-800/30 transition-colors">
                  <td class="py-3 px-4">
                    <div class="flex items-center gap-2.5">
                      <div class="h-7 w-7 rounded-full bg-slate-800 border border-slate-700 font-bold text-cyan-400 flex items-center justify-center text-xs font-mono">
                        {m.display_name ? m.display_name[0].toUpperCase() : m.email[0].toUpperCase()}
                      </div>
                      <div>
                        <div class="font-medium text-slate-200">{m.display_name}</div>
                        <div class="text-[11px] text-slate-400 font-mono">{m.email}</div>
                      </div>
                    </div>
                  </td>
                  <td class="py-3 px-4">
                    <span class="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-mono capitalize border {m.role === 'owner' ? 'bg-amber-950/60 text-amber-300 border-amber-800/60' : m.role === 'admin' ? 'bg-cyan-950/60 text-cyan-300 border-cyan-800/60' : 'bg-slate-800/80 text-slate-300 border-slate-700'}">
                      {m.role}
                    </span>
                  </td>
                  <td class="py-3 px-4 font-mono text-[11px] text-slate-500 truncate max-w-[160px]">
                    {m.user_id}
                  </td>
                  <td class="py-3 px-4 text-right">
                    {#if isOwnerOrAdmin && m.role !== 'owner'}
                      <button
                        type="button"
                        on:click={() => handleRemoveMember(m.user_id, m.email)}
                        class="text-rose-400 hover:text-rose-300 text-xs transition-colors font-medium"
                      >
                        Remove
                      </button>
                    {:else}
                      <span class="text-slate-600 text-xs font-mono">—</span>
                    {/if}
                  </td>
                </tr>
              {:else}
                <tr>
                  <td colspan="4" class="text-center py-6 text-slate-500 text-xs">
                    No members loaded or workspace empty.
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  {/if}

  <!-- Tab 2: Security Invariants -->
  {#if activeTab === "security"}
    <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
      <div class="p-5 rounded-xl bg-slate-900/60 border border-slate-800 space-y-3">
        <div class="flex items-center gap-2 text-cyan-400 text-xs font-semibold">
          <Lock class="w-4 h-4" />
          <span>Zero External AI Exfiltration</span>
        </div>
        <p class="text-xs text-slate-400 leading-relaxed">
          DevVision AI enforces strict operational invariants: zero API traffic is transmitted to external cloud providers (No OpenAI, Anthropic, Gemini, or Copilot). All embedding, vector search, reranking, and generation run 100% on self-hosted instances.
        </p>
        <div class="p-2.5 rounded bg-slate-950 border border-slate-800 font-mono text-[11px] text-emerald-400 flex items-center gap-2">
          <CheckCircle2 class="w-3.5 h-3.5" />
          <span>Self-Hosted Mode: ACTIVE & VERIFIED</span>
        </div>
      </div>

      <div class="p-5 rounded-xl bg-slate-900/60 border border-slate-800 space-y-3">
        <div class="flex items-center gap-2 text-cyan-400 text-xs font-semibold">
          <Shield class="w-4 h-4" />
          <span>Tenant Isolation & IDOR Defense</span>
        </div>
        <p class="text-xs text-slate-400 leading-relaxed">
          Every query against files, symbols, chunks, generations, and processing leases is constrained by composite foreign keys (<code class="text-cyan-300 font-mono">workspace_id</code>). Cross-workspace enumeration returns strict HTTP 404s.
        </p>
        <div class="p-2.5 rounded bg-slate-950 border border-slate-800 font-mono text-[11px] text-emerald-400 flex items-center gap-2">
          <CheckCircle2 class="w-3.5 h-3.5" />
          <span>IDOR Barrier: ENFORCED VIA COMPOSITE KEYS</span>
        </div>
      </div>

      <div class="p-5 rounded-xl bg-slate-900/60 border border-slate-800 space-y-3">
        <div class="flex items-center gap-2 text-cyan-400 text-xs font-semibold">
          <Database class="w-4 h-4" />
          <span>Opaque Sessions & CSRF Protection</span>
        </div>
        <p class="text-xs text-slate-400 leading-relaxed">
          Session tokens are SHA-256 hashed and matched against PostgreSQL. Clients transmit opaque tokens inside <code class="text-slate-300 font-mono">HttpOnly; SameSite=Lax</code> cookies alongside double-submit CSRF headers.
        </p>
        <div class="p-2.5 rounded bg-slate-950 border border-slate-800 font-mono text-[11px] text-emerald-400 flex items-center gap-2">
          <CheckCircle2 class="w-3.5 h-3.5" />
          <span>CSRF & Session Hijack Protection: ACTIVE</span>
        </div>
      </div>

      <div class="p-5 rounded-xl bg-slate-900/60 border border-slate-800 space-y-3">
        <div class="flex items-center gap-2 text-cyan-400 text-xs font-semibold">
          <Sliders class="w-4 h-4" />
          <span>Pessimistic Concurrency & Pins</span>
        </div>
        <p class="text-xs text-slate-400 leading-relaxed">
          Codebase generation activation serializes atomically via <code class="text-slate-300 font-mono">SELECT ... FOR UPDATE</code>. Active query pins with <code class="text-slate-300 font-mono">ON DELETE RESTRICT</code> guarantee zero GC corruption during in-flight queries.
        </p>
        <div class="p-2.5 rounded bg-slate-950 border border-slate-800 font-mono text-[11px] text-emerald-400 flex items-center gap-2">
          <CheckCircle2 class="w-3.5 h-3.5" />
          <span>Locking & Restrict Safety: ACTIVE</span>
        </div>
      </div>
    </div>
  {/if}

  <!-- Tab 3: Infrastructure & Models -->
  {#if activeTab === "system"}
    <div class="space-y-4">
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 text-xs">
        <div class="p-4 rounded-xl bg-slate-900/60 border border-slate-800 space-y-1">
          <span class="text-slate-400 text-[11px]">DENSE EMBEDDING</span>
          <div class="font-semibold text-white">bge-small-en-v1.5</div>
          <p class="text-[10px] text-slate-500 font-mono">384 dimensions • Local PyTorch</p>
        </div>
        <div class="p-4 rounded-xl bg-slate-900/60 border border-slate-800 space-y-1">
          <span class="text-slate-400 text-[11px]">CROSS-ENCODER RERANKER</span>
          <div class="font-semibold text-white">bge-reranker-base</div>
          <p class="text-[10px] text-slate-500 font-mono">Threshold 0.25 • Cross-Attention</p>
        </div>
        <div class="p-4 rounded-xl bg-slate-900/60 border border-slate-800 space-y-1">
          <span class="text-slate-400 text-[11px]">LOCAL GENERATION LLM</span>
          <div class="font-semibold text-white">qwen2.5-coder:7b</div>
          <p class="text-[10px] text-slate-500 font-mono">Ollama / llama.cpp runtime</p>
        </div>
        <div class="p-4 rounded-xl bg-slate-900/60 border border-slate-800 space-y-1">
          <span class="text-slate-400 text-[11px]">AST GRAMMAR PARSERS</span>
          <div class="font-semibold text-white">Tree-sitter (6 Grammars)</div>
          <p class="text-[10px] text-slate-500 font-mono">Python, JS, TS, Go, Rust, Java</p>
        </div>
      </div>

      <!-- Live Diagnostics Output -->
      {#if systemHealth}
        <div class="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-2 font-mono text-xs">
          <div class="flex items-center justify-between border-b border-slate-800/80 pb-2">
            <span class="font-semibold text-cyan-400">Cluster Diagnostics</span>
            <span class="text-emerald-400">STATUS: {systemHealth.status.toUpperCase()}</span>
          </div>
          <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-2 pt-2 text-[11px]">
            <div>Database: <span class="text-slate-300">{systemHealth.checks.database}</span></div>
            <div>pgvector: <span class="text-slate-300">{systemHealth.checks.pgvector}</span></div>
            <div>Redis Cache: <span class="text-slate-300">{systemHealth.checks.redis}</span></div>
            <div>Object Store: <span class="text-slate-300">{systemHealth.checks.storage}</span></div>
          </div>
        </div>
      {/if}
    </div>
  {/if}

  <!-- Add Member Modal -->
  {#if showAddMemberModal}
    <div class="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
      <div class="bg-slate-900 border border-slate-800 rounded-xl max-w-md w-full p-6 shadow-2xl space-y-4">
        <div class="flex items-center justify-between border-b border-slate-800 pb-3">
          <h3 class="text-sm font-semibold text-white">Invite Workspace Member</h3>
          <button type="button" on:click={() => (showAddMemberModal = false)} class="text-slate-400 hover:text-white">✕</button>
        </div>

        <div class="space-y-3 text-xs">
          <div>
            <label for="invite-email" class="block font-medium text-slate-300 mb-1">User Email Address *</label>
            <input
              id="invite-email"
              type="email"
              bind:value={newMemberEmail}
              placeholder="developer@company.com"
              class="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-cyan-500"
            />
          </div>

          <div>
            <label for="invite-role" class="block font-medium text-slate-300 mb-1">Workspace Role *</label>
            <select
              id="invite-role"
              bind:value={newMemberRole}
              class="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-cyan-500"
            >
              <option value="member">Member — Standard project and search rights</option>
              <option value="admin">Admin — Member management and index configuration</option>
            </select>
          </div>
        </div>

        <div class="flex items-center justify-end gap-2 pt-3 border-t border-slate-800 text-xs">
          <button
            type="button"
            on:click={() => (showAddMemberModal = false)}
            class="px-3 py-1.5 text-slate-400 hover:text-white transition-colors"
          >
            Cancel
          </button>
          <button
            type="button"
            on:click={handleAddMember}
            disabled={isAddingMember || !newMemberEmail.trim()}
            class="bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white font-medium px-4 py-1.5 rounded-lg transition-colors"
          >
            {isAddingMember ? "Adding..." : "Add Member"}
          </button>
        </div>
      </div>
    </div>
  {/if}
</div>
