<script lang="ts">
  import { onMount } from "svelte";
  import { page } from "$app/stores";
  import { api } from "$lib/api/client";
  import { activeWorkspace } from "$lib/stores/workspace";
  import type {
    CodebaseItem,
    CodebaseGenerationResponse,
    CodebaseFileItem,
    CodebaseSymbolItem,
    CodebaseQueryResponse,
    CodebaseCitationItem,
    GitHubRepositorySummary,
    GitHubSyncRun,
  } from "$lib/api/types";

  let codebaseId = $page.params.id;
  let codebase: CodebaseItem | null = null;
  let generations: CodebaseGenerationResponse[] = [];
  let files: CodebaseFileItem[] = [];
  let symbols: CodebaseSymbolItem[] = [];

  // GitHub Integration & Synchronization State
  let githubRepo: GitHubRepositorySummary | null = null;
  let syncRuns: GitHubSyncRun[] = [];
  let isLoadingSyncs = false;
  let isSyncing = false;
  let syncBranch = "";
  let forceSync = false;
  let syncMessage = "";

  let activeTab: "query" | "files" | "symbols" | "generations" | "sync" = "query";
  let isLoading = false;
  let actionError = "";

  // Query Tab State
  let queryText = "";
  let isQuerying = false;
  let queryResult: CodebaseQueryResponse | null = null;
  let queryError = "";
  let selectedCitation: CodebaseCitationItem | null = null;

  // Search/Filter in Explorer
  let symbolFilter = "";
  let fileFilter = "";

  $: currentWorkspaceId = $activeWorkspace?.id;
  $: if (currentWorkspaceId && codebaseId) {
    loadAll(currentWorkspaceId, codebaseId);
  }

  async function loadAll(workspaceId: string, cbId: string) {
    isLoading = true;
    actionError = "";

    const cbRes = await api.getCodebase(workspaceId, cbId);
    if (cbRes.success && cbRes.data) {
      codebase = cbRes.data;
    } else {
      actionError = cbRes.error || "Failed to load codebase.";
      isLoading = false;
      return;
    }

    // Load status / generations
    const genRes = await api.getCodebaseStatus(workspaceId, cbId);
    if (genRes.success && genRes.data) {
      generations = genRes.data;
    }

    // Load files
    const filesRes = await api.listCodebaseFiles(workspaceId, cbId, 100);
    if (filesRes.success && filesRes.data) {
      files = filesRes.data.items;
    }

    // Load symbols
    const symRes = await api.listCodebaseSymbols(workspaceId, cbId, undefined, 100);
    if (symRes.success && symRes.data) {
      symbols = symRes.data.items;
    }

    // Load attached GitHub repository, if any
    const ghRes = await api.getGitHubRepositoryByCodebase(workspaceId, cbId);
    if (ghRes.success && ghRes.data) {
      githubRepo = ghRes.data;
      syncBranch = ghRes.data.default_branch;
      await loadSyncRuns(workspaceId, ghRes.data.id);
    } else {
      githubRepo = null;
      syncRuns = [];
    }

    isLoading = false;
  }

  async function loadSyncRuns(workspaceId: string, repoId: string) {
    isLoadingSyncs = true;
    const runsRes = await api.listGitHubSyncRuns(workspaceId, repoId);
    isLoadingSyncs = false;
    if (runsRes.success && runsRes.data) {
      syncRuns = runsRes.data.items;
    }
  }

  async function handleTriggerSync() {
    if (!currentWorkspaceId || !codebaseId || !githubRepo) return;
    isSyncing = true;
    actionError = "";
    syncMessage = "";

    const res = await api.triggerGitHubSync(currentWorkspaceId, githubRepo.id, {
      ref: syncBranch.trim() || undefined,
      force: forceSync,
    });
    isSyncing = false;

    if (res.success && res.data) {
      syncMessage = `Sync run completed! Status: ${res.data.status} (Commit: ${res.data.commit_sha?.substring(0, 7) || 'latest'})`;
      // Reload codebase details, generations, and sync history
      await loadAll(currentWorkspaceId, codebaseId);
    } else {
      actionError = res.error || "GitHub synchronization failed.";
    }
  }

  async function handleQuery() {
    if (!currentWorkspaceId || !codebaseId || !queryText.trim()) return;
    isQuerying = true;
    queryError = "";
    queryResult = null;
    selectedCitation = null;

    const res = await api.queryCodebase(currentWorkspaceId, codebaseId, queryText.trim(), 8);
    isQuerying = false;

    if (res.success && res.data) {
      queryResult = res.data;
    } else {
      queryError = res.error || "Failed to execute codebase query.";
    }
  }

  $: filteredFiles = files.filter(
    (f) => !fileFilter || f.file_path.toLowerCase().includes(fileFilter.toLowerCase())
  );

  $: filteredSymbols = symbols.filter(
    (s) => !symbolFilter || s.name.toLowerCase().includes(symbolFilter.toLowerCase())
  );
</script>

<div class="space-y-6">
  <!-- Top Navigation & Details Header -->
  <div class="border-b border-slate-800 pb-5">
    <div class="flex items-center gap-2 text-xs text-slate-400 mb-2">
      <a href="/codebases" class="hover:text-cyan-400 transition-colors">Codebases</a>
      <span>/</span>
      <span class="text-slate-200">{codebase?.name || "Loading..."}</span>
    </div>

    {#if codebase}
      <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div class="flex items-center gap-3">
            <h1 class="text-xl font-bold tracking-tight text-white">{codebase.name}</h1>
            {#if codebase.is_indexed}
              <span class="inline-flex items-center gap-1.5 text-[11px] font-medium px-2.5 py-0.5 rounded-full bg-emerald-950/80 text-emerald-400 border border-emerald-800/60">
                <span class="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                Active Generation
              </span>
            {:else}
              <span class="inline-flex items-center gap-1.5 text-[11px] font-medium px-2.5 py-0.5 rounded-full bg-amber-950/80 text-amber-400 border border-amber-800/60">
                Awaiting Indexing
              </span>
            {/if}
          </div>
          <div class="flex items-center gap-4 text-xs text-slate-400 mt-2 font-mono">
            <span>Branch: <strong class="text-slate-200">{codebase.default_branch}</strong></span>
            <span>•</span>
            <span>Files: <strong class="text-slate-200">{files.length}</strong></span>
            <span>•</span>
            <span>Symbols: <strong class="text-slate-200">{symbols.length}</strong></span>
          </div>
        </div>

        <div class="flex items-center gap-2">
          <a
            href="/codebases"
            class="px-3 py-1.5 rounded-lg border border-slate-700 bg-slate-800 hover:bg-slate-700 text-xs text-slate-300 transition-colors"
          >
            ← Back
          </a>
        </div>
      </div>
    {/if}
  </div>

  {#if actionError}
    <div class="p-3 bg-rose-950/60 border border-rose-800/80 rounded-lg text-rose-300 text-xs">
      {actionError}
    </div>
  {/if}

  <!-- Tab Navigation -->
  <div class="flex items-center gap-1 border-b border-slate-800 text-xs">
    <button
      on:click={() => (activeTab = "query")}
      class={`px-4 py-2 font-medium border-b-2 transition-colors ${
        activeTab === "query"
          ? "border-cyan-500 text-cyan-400"
          : "border-transparent text-slate-400 hover:text-slate-200"
      }`}
    >
      Code Q&A & Search
    </button>
    <button
      on:click={() => (activeTab = "files")}
      class={`px-4 py-2 font-medium border-b-2 transition-colors ${
        activeTab === "files"
          ? "border-cyan-500 text-cyan-400"
          : "border-transparent text-slate-400 hover:text-slate-200"
      }`}
    >
      Files ({files.length})
    </button>
    <button
      on:click={() => (activeTab = "symbols")}
      class={`px-4 py-2 font-medium border-b-2 transition-colors ${
        activeTab === "symbols"
          ? "border-cyan-500 text-cyan-400"
          : "border-transparent text-slate-400 hover:text-slate-200"
      }`}
    >
      Symbols ({symbols.length})
    </button>
    <button
      on:click={() => (activeTab = "generations")}
      class={`px-4 py-2 font-medium border-b-2 transition-colors ${
        activeTab === "generations"
          ? "border-cyan-500 text-cyan-400"
          : "border-transparent text-slate-400 hover:text-slate-200"
      }`}
    >
      Generations ({generations.length})
    </button>
    {#if githubRepo}
      <button
        on:click={() => (activeTab = "sync")}
        class={`px-4 py-2 font-medium border-b-2 transition-colors flex items-center gap-1.5 ${
          activeTab === "sync"
            ? "border-cyan-500 text-cyan-400"
            : "border-transparent text-slate-400 hover:text-slate-200"
        }`}
      >
        <svg class="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24">
          <path fill-rule="evenodd" clip-rule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" />
        </svg>
        GitHub Sync ({syncRuns.length})
      </button>
    {/if}
  </div>

  <!-- Tab 1: Code Q&A -->
  {#if activeTab === "query"}
    <div class="space-y-4">
      <div class="bg-slate-900/60 border border-slate-800 rounded-xl p-4">
        <form on:submit|preventDefault={handleQuery} class="space-y-3">
          <label for="codebase-qa-input" class="block text-xs font-semibold text-slate-200">
            Ask questions about this codebase:
          </label>
          <div class="flex gap-2">
            <input
              id="codebase-qa-input"
              type="text"
              bind:value={queryText}
              placeholder="e.g. How is user authentication implemented? Or where is verify_token defined?"
              class="flex-1 bg-slate-950 border border-slate-800 rounded-lg px-3.5 py-2 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500"
            />
            <button
              type="submit"
              disabled={isQuerying || !queryText.trim()}
              class="bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 disabled:opacity-50 text-white font-medium text-xs px-5 py-2 rounded-lg transition-all flex items-center gap-2"
            >
              {#if isQuerying}
                <div class="animate-spin rounded-full h-3.5 w-3.5 border-b-2 border-white"></div>
                Analyzing...
              {:else}
                Ask Code
              {/if}
            </button>
          </div>
        </form>
      </div>

      {#if queryError}
        <div class="p-3 bg-rose-950/60 border border-rose-800/80 rounded-lg text-rose-300 text-xs">
          {queryError}
        </div>
      {/if}

      {#if queryResult}
        <div class="bg-slate-900/80 border border-slate-800 rounded-xl p-5 space-y-4">
          <div class="flex items-center justify-between border-b border-slate-800/80 pb-3 text-xs">
            <span class="font-semibold text-white">Grounded Answer</span>
            <div class="flex items-center gap-3 text-slate-400 font-mono text-[11px]">
              <span>Strategy: <span class="text-cyan-400">{queryResult.retrieval_strategy}</span></span>
              <span>•</span>
              <span>Latency: <span class="text-emerald-400">{queryResult.latency_ms}ms</span></span>
            </div>
          </div>

          <div class="text-xs text-slate-200 whitespace-pre-wrap leading-relaxed">
            {queryResult.answer}
          </div>

          <!-- Citations Section -->
          {#if queryResult.citations.length > 0}
            <div class="pt-4 border-t border-slate-800/80 space-y-2">
              <span class="text-xs font-semibold text-slate-300 block">Verified Code Citations:</span>
              <div class="grid grid-cols-1 md:grid-cols-2 gap-2">
                {#each queryResult.citations as cit}
                  <button
                    type="button"
                    on:click={() => (selectedCitation = cit)}
                    class="p-3 bg-slate-950/60 hover:bg-slate-950 border border-slate-800 hover:border-cyan-500/60 rounded-lg cursor-pointer transition-colors text-xs font-mono text-left w-full"
                  >
                    <div class="flex items-center justify-between text-cyan-400 font-medium">
                      <span>{cit.file_path}</span>
                      <span class="text-[11px] text-slate-400">L{cit.start_line}-{cit.end_line}</span>
                    </div>
                    <p class="text-slate-400 text-[11px] truncate mt-1">
                      {cit.snippet_preview.split("\n")[0]}
                    </p>
                  </button>
                {/each}
              </div>
            </div>
          {/if}
        </div>
      {/if}

      <!-- Citation Snippet Modal -->
      {#if selectedCitation}
        <div class="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div class="bg-slate-900 border border-slate-800 rounded-xl max-w-2xl w-full p-6 shadow-2xl space-y-4">
            <div class="flex items-center justify-between border-b border-slate-800 pb-3">
              <div>
                <h3 class="text-sm font-semibold text-white font-mono">{selectedCitation.file_path}</h3>
                <span class="text-xs text-slate-400 font-mono">Lines {selectedCitation.start_line} – {selectedCitation.end_line}</span>
              </div>
              <button on:click={() => (selectedCitation = null)} class="text-slate-400 hover:text-white">✕</button>
            </div>

            <pre class="bg-slate-950 border border-slate-800 rounded-lg p-4 font-mono text-xs text-slate-200 overflow-x-auto max-h-96"><code>{selectedCitation.snippet_preview}</code></pre>

            <div class="flex justify-end pt-2">
              <button
                on:click={() => (selectedCitation = null)}
                class="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-xs text-white rounded-lg transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      {/if}
    </div>

  <!-- Tab 2: Files Explorer -->
  {:else if activeTab === "files"}
    <div class="space-y-4">
      <div class="flex items-center justify-between gap-3">
        <input
          type="text"
          bind:value={fileFilter}
          placeholder="Filter files by path..."
          class="w-full sm:max-w-xs bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-white focus:outline-none focus:border-cyan-500"
        />
        <span class="text-xs text-slate-400 font-mono">{filteredFiles.length} files</span>
      </div>

      <div class="bg-slate-900/60 border border-slate-800 rounded-xl divide-y divide-slate-800/60 overflow-hidden">
        {#each filteredFiles as f (f.id)}
          <div class="p-3 hover:bg-slate-850/50 flex items-center justify-between text-xs font-mono transition-colors">
            <div class="flex items-center gap-2">
              <span class="px-1.5 py-0.5 rounded bg-slate-800 text-cyan-400 text-[10px] font-semibold uppercase">
                {f.language}
              </span>
              <span class="text-slate-200 font-medium">{f.file_path}</span>
            </div>
            <div class="flex items-center gap-4 text-slate-400 text-[11px]">
              <span>{f.line_count} lines</span>
              <span>{(f.byte_size / 1024).toFixed(1)} KB</span>
            </div>
          </div>
        {/each}
      </div>
    </div>

  <!-- Tab 3: Symbols Explorer -->
  {:else if activeTab === "symbols"}
    <div class="space-y-4">
      <div class="flex items-center justify-between gap-3">
        <input
          type="text"
          bind:value={symbolFilter}
          placeholder="Filter symbols by name..."
          class="w-full sm:max-w-xs bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-white focus:outline-none focus:border-cyan-500"
        />
        <span class="text-xs text-slate-400 font-mono">{filteredSymbols.length} symbols</span>
      </div>

      <div class="bg-slate-900/60 border border-slate-800 rounded-xl divide-y divide-slate-800/60 overflow-hidden">
        {#each filteredSymbols as sym (sym.id)}
          <div class="p-3 hover:bg-slate-850/50 flex items-center justify-between text-xs font-mono transition-colors">
            <div>
              <div class="flex items-center gap-2">
                <span class="px-1.5 py-0.5 rounded bg-slate-800 text-purple-400 text-[10px] font-semibold">
                  {sym.symbol_type}
                </span>
                <span class="text-white font-semibold">{sym.name}</span>
              </div>
              {#if sym.signature}
                <div class="text-[11px] text-slate-400 mt-1 truncate max-w-xl">
                  {sym.signature}
                </div>
              {/if}
            </div>
            <div class="text-[11px] text-slate-400">
              Lines {sym.start_line}–{sym.end_line}
            </div>
          </div>
        {/each}
      </div>
    </div>

  <!-- Tab 4: Generations -->
  {:else if activeTab === "generations"}
    <div class="space-y-4">
      <div class="bg-slate-900/60 border border-slate-800 rounded-xl divide-y divide-slate-800/60 overflow-hidden">
        {#each generations as gen (gen.id)}
          <div class="p-4 flex items-center justify-between text-xs font-mono">
            <div>
              <div class="flex items-center gap-2">
                <span class="font-bold text-white text-sm">Generation #{gen.generation_number}</span>
                {#if gen.status === "active"}
                  <span class="px-2 py-0.5 rounded-full bg-emerald-950 text-emerald-400 border border-emerald-800 text-[10px]">
                    active
                  </span>
                {:else if gen.status === "retired"}
                  <span class="px-2 py-0.5 rounded-full bg-slate-800 text-slate-400 text-[10px]">
                    retired
                  </span>
                {:else if gen.status === "building"}
                  <span class="px-2 py-0.5 rounded-full bg-cyan-950 text-cyan-400 border border-cyan-800 text-[10px]">
                    building
                  </span>
                {:else}
                  <span class="px-2 py-0.5 rounded-full bg-rose-950 text-rose-400 border border-rose-800 text-[10px]">
                    failed
                  </span>
                {/if}
              </div>
              <div class="text-[11px] text-slate-400 mt-1">
                Pipeline: {gen.pipeline_version} | Model Rev: {gen.embedding_model_revision}
              </div>
            </div>
            <div class="text-right text-[11px] text-slate-400 space-y-1">
              <div>{gen.total_files} files • {gen.total_symbols} symbols • {gen.total_chunks} chunks</div>
              <div class="text-slate-500">{new Date(gen.created_at).toLocaleString()}</div>
            </div>
          </div>
        {/each}
      </div>
    </div>

  <!-- Tab 5: GitHub Synchronization -->
  {:else if activeTab === "sync" && githubRepo}
    <div class="space-y-6">
      <!-- Sync Controls Card -->
      <div class="bg-slate-900/60 border border-slate-800 rounded-xl p-5 space-y-4">
        <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h3 class="text-sm font-semibold text-white flex items-center gap-2">
              <svg class="w-4 h-4 text-cyan-400" fill="currentColor" viewBox="0 0 24 24">
                <path fill-rule="evenodd" clip-rule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" />
              </svg>
              GitHub Repository Synchronization
            </h3>
            <p class="text-xs text-slate-400 mt-1 font-mono">
              Linked to <span class="text-white font-medium">{githubRepo.full_name}</span> (ID: {githubRepo.github_repo_id})
            </p>
          </div>

          <div class="flex items-center gap-3">
            <div class="flex items-center gap-2">
              <input
                type="text"
                bind:value={syncBranch}
                placeholder="Branch or tag (e.g. main)"
                class="bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500"
              />
              <label class="flex items-center gap-1.5 text-xs text-slate-400 cursor-pointer">
                <input
                  type="checkbox"
                  bind:checked={forceSync}
                  class="rounded bg-slate-950 border-slate-800 text-cyan-600 focus:ring-0"
                />
                Force
              </label>
            </div>

            <button
              on:click={handleTriggerSync}
              disabled={isSyncing}
              class="px-4 py-1.5 rounded-lg bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white font-medium text-xs transition-all shadow-md shadow-cyan-600/20 disabled:opacity-50 flex items-center gap-1.5"
            >
              {#if isSyncing}
                <div class="animate-spin rounded-full h-3.5 w-3.5 border-b-2 border-white"></div>
                Syncing...
              {:else}
                <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
                Sync Now
              {/if}
            </button>
          </div>
        </div>

        {#if syncMessage}
          <div class="p-3 bg-emerald-950/70 border border-emerald-800/80 rounded-lg text-emerald-300 text-xs">
            {syncMessage}
          </div>
        {/if}
      </div>

      <!-- Sync Runs History Table -->
      <div class="space-y-3">
        <h4 class="text-xs font-semibold uppercase tracking-wider text-slate-400">Synchronization Runs</h4>
        <div class="bg-slate-900/60 border border-slate-800 rounded-xl divide-y divide-slate-800/60 overflow-hidden">
          {#if isLoadingSyncs}
            <div class="py-8 text-center text-xs text-slate-400 font-mono">Loading sync history...</div>
          {:else if syncRuns.length === 0}
            <div class="py-8 text-center text-xs text-slate-500 font-mono">No sync runs recorded yet.</div>
          {:else}
            {#each syncRuns as run (run.id)}
              <div class="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs font-mono">
                <div>
                  <div class="flex items-center gap-2">
                    <span class="font-bold text-white">Ref: {run.requested_ref}</span>
                    {#if run.status === "completed"}
                      <span class="px-2 py-0.5 rounded-full bg-emerald-950 text-emerald-400 border border-emerald-800 text-[10px]">
                        completed
                      </span>
                    {:else if run.status === "failed"}
                      <span class="px-2 py-0.5 rounded-full bg-rose-950 text-rose-400 border border-rose-800 text-[10px]">
                        failed
                      </span>
                    {:else}
                      <span class="px-2 py-0.5 rounded-full bg-cyan-950 text-cyan-400 border border-cyan-800 text-[10px]">
                        {run.status}
                      </span>
                    {/if}
                  </div>
                  <div class="text-[11px] text-slate-400 mt-1">
                    Commit: <span class="text-cyan-400 font-bold">{run.commit_sha ? run.commit_sha.substring(0, 10) : "pending"}</span>
                    {#if run.error_message}
                      &bull; <span class="text-rose-400">{run.error_message}</span>
                    {/if}
                  </div>
                </div>

                <div class="text-right text-[11px] text-slate-400 space-y-1">
                  <div>{run.file_count} files &bull; {(run.byte_count / 1024).toFixed(1)} KB</div>
                  <div class="text-slate-500">{new Date(run.created_at).toLocaleString()}</div>
                </div>
              </div>
            {/each}
          {/if}
        </div>
      </div>
    </div>
  {/if}
</div>
